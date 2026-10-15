"""Official API adapters. Only user codes and sanitized status leave this module."""

import secrets
import threading
import time
from collections import defaultdict
from urllib.parse import urlsplit

import httpx

from app.security import Vault
from app.store import Store

TRAKT_API = "https://api.trakt.tv"
TRAKT_AUTH = "https://auth.trakt.tv"
RD_API = "https://api.real-debrid.com/rest/1.0"
RD_AUTH = "https://api.real-debrid.com/oauth/v2"
TMDB_API = "https://api.themoviedb.org/3"
RD_GRANT = "http://oauth.net/grant_type/device/1.0"
SERVICES = {"trakt", "real_debrid"}


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 502, retry_after: int = 0):
        self.message, self.status, self.retry_after = message, status, retry_after
        super().__init__(message)


class Services:
    def __init__(self, store: Store, vault: Vault, transport=None):
        self.store, self.vault = store, vault
        self.http = httpx.Client(transport=transport, timeout=httpx.Timeout(12, connect=5),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=2),
            follow_redirects=False, headers={"User-Agent": "VizioMedia/0.2 (self-hosted)"})
        self.locks = defaultdict(threading.RLock)

    def close(self):
        self.http.close()

    def config(self, service: str) -> dict:
        return self.vault.open(self.store.config(service))

    def configuration_status(self) -> dict:
        return {
            "tmdb": {"configured": bool(self.config("tmdb").get("read_token"))},
            "trakt": {"configured": bool(self.config("trakt").get("client_id"))},
            "real_debrid": {"configured": bool(self.config("real_debrid").get("client_id")), "personal_token_supported": True},
        }

    def raw(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            return self.http.request(method, url, **kwargs)
        except httpx.HTTPError:
            raise ServiceError("The service could not be reached. Try again shortly.", 503) from None

    @staticmethod
    def json(response: httpx.Response):
        if len(response.content) > 2 * 1024 * 1024:
            raise ServiceError("The service response was too large.")
        try:
            return response.json()
        except ValueError:
            raise ServiceError("The service returned an unreadable response.") from None

    def checked(self, response: httpx.Response):
        if response.status_code == 429:
            raise ServiceError("The service is busy. Wait before trying again.", 429, self.retry_delay(response))
        if response.status_code in {401,403}:
            raise ServiceError("The service rejected these credentials. Check setup or reconnect the account.", 401)
        if response.status_code >= 400 or response.is_redirect:
            raise ServiceError("The service could not complete that request. Try again shortly.")
        return self.json(response)

    @staticmethod
    def retry_delay(response: httpx.Response) -> int:
        try:
            return max(5, min(300, int(float(response.headers.get("Retry-After", "30")))))
        except ValueError:
            return 30

    def trakt_headers(self, access_token: str | None = None) -> dict:
        client_id = self.config("trakt").get("client_id")
        if not client_id:
            raise ServiceError("Set up the Trakt application in Account manager first.", 409)
        headers = {"trakt-api-key": client_id, "trakt-api-version": "2", "Content-Type": "application/json"}
        if access_token:
            headers["Authorization"] = "Bearer " + access_token
        return headers

    def tmdb(self, path: str, params: dict | None = None):
        token = self.config("tmdb").get("read_token")
        if not token:
            raise ServiceError("Set up TMDB in Account manager to search the full catalog.", 409)
        return self.checked(self.raw("GET", TMDB_API+path, headers={"Authorization": "Bearer "+token}, params=params))

    def trakt(self, path: str, params: dict | None = None, profile_id: str | None = None):
        if profile_id:
            return self.authorized(profile_id,"trakt","GET",path,params=params)
        return self.checked(self.raw("GET",TRAKT_API+path,headers=self.trakt_headers(),params=params))

    def configure(self, service: str, values: dict):
        with self.locks[("config",service)]:
            previous = self.config(service)
            updated = {**previous, **{k:v.strip() for k,v in values.items() if isinstance(v,str) and v.strip()}}
            if service in SERVICES and previous != updated and self.store.linked_count(service):
                raise ServiceError("Disconnect linked accounts before changing this application's settings.",409)
            if service in SERVICES and previous != updated and self.store.pending_count(service):
                raise ServiceError("Cancel pending sign-ins or wait for their codes to expire before changing application settings.",409)
            if service == "tmdb":
                token = updated.get("read_token", "")
                if not token:
                    raise ServiceError("Enter a TMDB API Read Access Token.",400)
                self.checked(self.raw("GET",TMDB_API+"/configuration",headers={"Authorization":"Bearer "+token}))
            elif service == "trakt":
                if not updated.get("client_id"):
                    raise ServiceError("Enter your Trakt application's client ID.",400)
                # The API validates the ID without starting a user's sign-in.
                headers={"trakt-api-key":updated["client_id"],"trakt-api-version":"2"}
                self.checked(self.raw("GET",TRAKT_API+"/movies/trending",headers=headers,params={"limit":1}))
                updated.setdefault("redirect_uri","urn:ietf:wg:oauth:2.0:oob")
            elif service == "real_debrid":
                if not updated.get("client_id"):
                    raise ServiceError("Enter your Real-Debrid application client ID, or use a personal token for this private installation.",400)
            else:
                raise ServiceError("Unknown service.",404)
            self.store.save_config(service,self.vault.seal(updated))

    def remove_configuration(self, service: str):
        with self.locks[("config",service)]:
            if self.store.linked_count(service):
                raise ServiceError("Disconnect linked accounts before removing application settings.",409)
            if self.store.pending_count(service):
                raise ServiceError("Cancel pending sign-ins or wait for their codes to expire before removing application settings.",409)
            self.store.delete_config(service)

    def status(self, profile_id: str) -> dict:
        result = {}
        setup = self.configuration_status()
        for service in sorted(SERVICES):
            account = self.store.account(profile_id,service)
            result[service] = {
                "configured": setup[service]["configured"],
                "state": account["status"] if account else "disconnected",
                "display_name": account["display_name"] if account else None,
                "expires_at": account["expires_at"] if account else None,
            }
        return result

    @staticmethod
    def verified_url(service: str, url: str) -> str:
        parsed = urlsplit(url)
        hosts = {"trakt.tv","www.trakt.tv","auth.trakt.tv","app.trakt.tv"} if service == "trakt" else {"real-debrid.com","www.real-debrid.com"}
        if parsed.scheme != "https" or parsed.hostname not in hosts or parsed.username or parsed.password or parsed.port not in {None,443}:
            raise ServiceError("The service returned an unexpected sign-in address.")
        return url

    def public_flow(self, flow: dict) -> dict:
        if flow["expires_at"] <= time.time() and flow["state"] == "pending":
            flow["state"] = "expired"
            flow["sealed"] = ""
            self.store.save_flow(flow)
        result = {"id":flow["id"],"service":flow["service"],"state":flow["state"],
                  "expires_at":flow["expires_at"],"interval":flow["interval"],
                  "retry_after":max(0,int(flow["next_poll"]-time.time()+1))}
        if flow["state"] == "pending":
            data = self.vault.open(flow["sealed"])
            result.update(user_code=data["user_code"],verification_url=data["verification_url"])
        return result

    def start(self, profile_id: str, service: str) -> dict:
        if service not in SERVICES:
            raise ServiceError("Unknown service.",404)
        with self.locks[("config",service)], self.locks[(profile_id,service)]:
            existing = self.store.pending_flow(profile_id,service)
            if existing:
                return self.public_flow(existing)
            account = self.store.account(profile_id,service)
            if account and account["status"] == "connected":
                raise ServiceError("This account is already connected. Disconnect it before linking another.",409)
            config = self.config(service)
            if not config.get("client_id"):
                raise ServiceError("Set up this application's client ID in Account manager on this PC first.",409)
            if service == "trakt":
                data = self.checked(self.raw("POST",TRAKT_AUTH+"/oauth/device/code",json={"client_id":config["client_id"]}))
            else:
                data = self.checked(self.raw("GET",RD_AUTH+"/device/code",params={"client_id":config["client_id"],"new_credentials":"yes"}))
            try:
                interval = max(1,min(60,float(data["interval"])))
                expires_at = time.time()+max(1,min(3600,float(data["expires_in"])))
                payload = {"device_code":str(data["device_code"]),"user_code":str(data["user_code"])[:64],
                    "verification_url": self.verified_url(service,str(data["verification_url"]))}
            except (KeyError,ValueError,TypeError):
                raise ServiceError("The service returned an incomplete sign-in code.") from None
            flow={"id":secrets.token_urlsafe(24),"profile_id":profile_id,"service":service,"state":"pending",
                  "sealed":self.vault.seal(payload),"expires_at":expires_at,"interval":interval,"next_poll":time.time()+interval}
            self.store.save_flow(flow)
            return self.public_flow(flow)

    def get_flow(self, profile_id: str, flow_id: str) -> dict:
        flow=self.store.flow(flow_id)
        if not flow or flow["profile_id"] != profile_id:
            raise ServiceError("Sign-in session not found.",404)
        return flow

    def cancel(self, profile_id: str, flow_id: str) -> dict:
        flow=self.get_flow(profile_id,flow_id)
        with self.locks[(profile_id,flow["service"])]:
            flow=self.get_flow(profile_id,flow_id)
            if flow["state"] == "pending":
                flow.update(state="cancelled",sealed="")
                self.store.save_flow(flow)
        return self.public_flow(flow)

    def poll(self, profile_id: str, flow_id: str) -> dict:
        initial=self.get_flow(profile_id,flow_id)
        service=initial["service"]
        with self.locks[(profile_id,service)]:
            flow=self.get_flow(profile_id,flow_id)
            status=self.public_flow(flow)
            if status["state"] != "pending" or flow["next_poll"]>time.time():
                return status
            flow["next_poll"]=time.time()+flow["interval"]
            self.store.save_flow(flow)  # Enforce interval even when an upstream request fails.
            data=self.vault.open(flow["sealed"])
            config=self.config(service)
            if service == "trakt":
                response=self.raw("POST",TRAKT_AUTH+"/oauth/device/token",json={"code":data["device_code"],"client_id":config["client_id"]})
            else:
                if "client_secret" not in data:
                    credentials=self.raw("GET",RD_AUTH+"/device/credentials",params={"client_id":config["client_id"],"code":data["device_code"]})
                    if credentials.status_code == 429:
                        flow["next_poll"]=time.time()+self.retry_delay(credentials)
                        self.store.save_flow(flow)
                        return self.public_flow(flow)
                    if credentials.status_code in {400,403,404}:
                        # RD documents an error until approval, without a precise HTTP mapping.
                        return self.public_flow(flow)
                    credentials_data=self.checked(credentials)
                    if not credentials_data.get("client_id") or not credentials_data.get("client_secret"):
                        return self.public_flow(flow)
                    data.update(client_id=credentials_data["client_id"],client_secret=credentials_data["client_secret"])
                    flow["sealed"]=self.vault.seal(data)
                    self.store.save_flow(flow)
                response=self.raw("POST",RD_AUTH+"/token",data={"client_id":data["client_id"],"client_secret":data["client_secret"],"code":data["device_code"],"grant_type":RD_GRANT})
            if response.status_code == 429:
                flow["next_poll"]=time.time()+self.retry_delay(response)
                self.store.save_flow(flow)
                return self.public_flow(flow)
            if service == "trakt" and response.status_code == 400:
                return self.public_flow(flow)
            if service == "trakt" and response.status_code in {404,409,410,418}:
                flow.update(state={404:"invalid",409:"used",410:"expired",418:"denied"}[response.status_code],sealed="")
                self.store.save_flow(flow)
                return self.public_flow(flow)
            tokens=self.checked(response)
            account=self.valid_tokens(tokens)
            if service == "real_debrid":
                account.update(client_id=data["client_id"],client_secret=data["client_secret"])
            # Token exchange succeeds exactly once. Persist before optional user-info calls.
            self.store.save_account(profile_id,service,self.vault.seal(account),"Connected account",account["expires_at"],flow_id=flow_id)
            self.identify(profile_id,service)
            return self.public_flow(self.get_flow(profile_id,flow_id))

    @staticmethod
    def valid_tokens(tokens: dict) -> dict:
        try:
            access=tokens["access_token"]
            refresh=tokens["refresh_token"]
            if not isinstance(access,str) or not access or not isinstance(refresh,str) or not refresh:
                raise ValueError()
            expires=float(tokens["expires_in"])
            if not 0 < expires < 400*86400:
                raise ValueError()
            return {"access_token":access,"refresh_token":refresh,"expires_at":time.time()+expires,"mode":"oauth"}
        except (KeyError,ValueError,TypeError):
            raise ServiceError("The service returned incomplete account credentials. Start sign-in again.") from None

    def personal_token(self, profile_id: str, token: str):
        response=self.raw("GET",RD_API+"/user",headers={"Authorization":"Bearer "+token})
        user=self.checked(response)
        with self.locks[(profile_id,"real_debrid")]:
            self.store.unlink(profile_id,"real_debrid")
            self.store.save_account(profile_id,"real_debrid",self.vault.seal({"access_token":token,"mode":"personal","expires_at":0}),str(user.get("username","Real-Debrid account"))[:80],0)

    def identify(self, profile_id: str, service: str, *, required: bool = False):
        try:
            user=self.authorized(profile_id,service,"GET","/users/settings" if service=="trakt" else "/user")
            name=user.get("user",{}).get("username") if service=="trakt" else user.get("username")
            if name:
                account=self.store.account(profile_id,service)
                self.store.save_account(profile_id,service,account["sealed"],str(name)[:80],account["expires_at"])
        except ServiceError:
            if required:
                raise
            pass  # Account remains linked even if the optional display-name request fails.

    def access(self, profile_id: str, service: str, *, force: bool = False) -> str:
        with self.locks[(profile_id,service)]:
            account=self.store.account(profile_id,service)
            if not account or account["status"] != "connected":
                raise ServiceError("Connect this service for the selected profile first.",401)
            data=self.vault.open(account["sealed"])
            if data.get("mode")=="personal" or (not force and account["expires_at"]>time.time()+60):
                return data["access_token"]
            config=self.config(service)
            if service=="trakt":
                payload={"client_id":config["client_id"],"refresh_token":data["refresh_token"],"grant_type":"refresh_token",
                    "redirect_uri":config.get("redirect_uri","urn:ietf:wg:oauth:2.0:oob")}
                if config.get("client_secret"):
                    payload["client_secret"]=config["client_secret"]
                response=self.raw("POST",TRAKT_AUTH+"/oauth/token",json=payload)
            else:
                response=self.raw("POST",RD_AUTH+"/token",data={"client_id":data["client_id"],"client_secret":data["client_secret"],"code":data["refresh_token"],"grant_type":RD_GRANT})
            if response.status_code in {400,401,403}:
                self.store.mark_account(profile_id,service,"reconnect_required")
                raise ServiceError("This account needs to be connected again.",401)
            replacement=self.valid_tokens(self.checked(response))
            data.update(replacement)
            # One transaction replaces both rotated tokens. No old refresh token is retried.
            self.store.save_account(profile_id,service,self.vault.seal(data),account["display_name"],data["expires_at"])
            return data["access_token"]

    def authorized(self, profile_id: str, service: str, method: str, path: str, **kwargs):
        with self.locks[(profile_id,service)]:
            access=self.access(profile_id,service)
            headers=self.trakt_headers(access) if service=="trakt" else {"Authorization":"Bearer "+access}
            base=TRAKT_API if service=="trakt" else RD_API
            response=self.raw(method,base+path,headers=headers,**kwargs)
            if response.status_code == 401:
                account=self.store.account(profile_id,service)
                if self.vault.open(account["sealed"]).get("mode")=="personal":
                    self.store.mark_account(profile_id,service,"reconnect_required")
                else:
                    access=self.access(profile_id,service,force=True)
                    headers=self.trakt_headers(access) if service=="trakt" else {"Authorization":"Bearer "+access}
                    response=self.raw(method,base+path,headers=headers,**kwargs)
                    if response.status_code==401:
                        self.store.mark_account(profile_id,service,"reconnect_required")
            return self.checked(response)

    def disconnect(self, profile_id: str, service: str) -> dict:
        if service not in SERVICES:
            raise ServiceError("Unknown service.",404)
        remote=False
        with self.locks[(profile_id,service)]:
            account=self.store.account(profile_id,service)
            if account:
                data=self.vault.open(account["sealed"])
                try:
                    if service=="trakt":
                        config=self.config(service)
                        payload={"client_id":config["client_id"],"token":data["access_token"]}
                        if config.get("client_secret"): payload["client_secret"]=config["client_secret"]
                        response=self.raw("POST",TRAKT_AUTH+"/oauth/revoke",json=payload)
                    else:
                        response=self.raw("GET",RD_API+"/disable_access_token",headers={"Authorization":"Bearer "+data["access_token"]})
                    remote=response.status_code in {200,204}
                except ServiceError:
                    pass
            self.store.unlink(profile_id,service)
        return {"state":"disconnected","remote_token_disabled":remote,
            "message":"Disconnected locally. Review authorized applications on the service website to remove any remaining grant."}
