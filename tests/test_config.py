"""Deployment configuration must fail closed before opening network listeners."""

import pytest

from app.config import Settings


def test_native_start_requires_explicit_tv_address(monkeypatch):
    monkeypatch.delenv("VIZIO_TV_IP",raising=False)
    with pytest.raises(ValueError,match="Set VIZIO_TV_IP"):
        Settings.from_env()


def test_deployment_reads_addresses_port_and_storage(monkeypatch,tmp_path):
    monkeypatch.setenv("VIZIO_TV_IP","192.0.2.20")
    monkeypatch.setenv("VIZIO_BIND_IP","192.0.2.10")
    monkeypatch.setenv("VIZIO_PORT","18765")
    monkeypatch.setenv("VIZIO_DATA_DIR",str(tmp_path/"private"))
    monkeypatch.setenv("VIZIO_MEDIA_DIR",str(tmp_path/"clips"))
    settings=Settings.from_env()
    assert settings.bind_ip=="192.0.2.10" and settings.tv_ip=="192.0.2.20"
    assert settings.port==18765
    assert settings.data_dir==tmp_path/"private" and settings.media_dir==tmp_path/"clips"


@pytest.mark.parametrize("bind,port",[("0.0.0.0",8765),("::",8765),("localhost",8765),("224.0.0.1",8765),("127.0.0.1",0),("127.0.0.1",65536)])
def test_invalid_bindings_and_ports_are_rejected(bind,port):
    with pytest.raises(ValueError):
        Settings(bind_ip=bind,port=port)
