# -*- coding: utf-8 -*-
"""
Testing possibilities to configure devices
"""
__author__ = 'Michal Ernst, Marcin Usielski'
__copyright__ = 'Copyright (C) 2018-2026, Nokia'
__email__ = 'michal.ernst@nokia.com, marcin.usielski@nokia.com'

import os

import pytest

from moler.util.moler_test import MolerTest
from moler.connection_observer import ConnectionObserver
from moler.device import DeviceFactory
from moler.exceptions import WrongUsage
from moler.device.unixlocal import UnixLocal


def test_get_device_may_not_use_both__name_and_device_class(device_factory):
    with pytest.raises(WrongUsage) as err:
        device_factory.get_device(name='UNIX_LOCAL', device_class='moler.device.unixlocal', connection_desc={},
                                  connection_hops={})
    assert "Use either 'name' or 'device_class' parameter (not both)" in str(err.value)


def test_get_device_must_use_either_name_or_device_class(device_factory):
    with pytest.raises(WrongUsage) as err:
        device_factory.get_device(connection_desc={}, connection_hops={})
    assert "Provide either 'name' or 'device_class' parameter (none given)" in str(err.value)


def test_can_select_device_by_name(device_config, device_factory):
    device_config.define_device(
        name="UNIX_LOCAL",
        device_class='moler.device.unixlocal.UnixLocal',
        connection_desc={
            "io_type": "terminal",
            "variant": "threaded"
        },
        connection_hops={},
    )
    device = device_factory.get_device(name='UNIX_LOCAL')

    assert device.__module__ == 'moler.device.unixlocal'
    assert device.__class__.__name__ == 'UnixLocal'
    assert device._state_prompts['UNIX_LOCAL'] == '^moler_bash#'


def test_can_select_device_by_name_with_initial_state_set(device_config, device_factory):
    device_config.define_device(
        name="UNIX_LOCAL",
        device_class='moler.device.unixlocal.UnixLocal',
        connection_desc={
            "io_type": "terminal",
            "variant": "threaded"
        },
        connection_hops={},
        initial_state="NOT_CONNECTED"
    )
    device = device_factory.get_device(name='UNIX_LOCAL')

    assert device.__module__ == 'moler.device.unixlocal'
    assert device.__class__.__name__ == 'UnixLocal'
    assert device.current_state == "NOT_CONNECTED"


def test_can_select_device_by_description(device_factory):
    device = device_factory.get_device(
        device_class='moler.device.unixlocal.UnixLocal',
        connection_desc={
            "io_type": "terminal",
            "variant": "threaded"
        },
        connection_hops={}
    )

    assert device.__module__ == 'moler.device.unixlocal'
    assert device.__class__.__name__ == 'UnixLocal'


def test_can_select_desc_device_by_default_connection_desc(device_factory):
    device = device_factory.get_device(
        device_class='moler.device.unixlocal.UnixLocal',
        connection_hops={}
    )

    assert device.__module__ == 'moler.device.unixlocal'
    assert device.__class__.__name__ == 'UnixLocal'


def test_can_select_named_device_by_default_connection_desc(device_config, device_factory):
    device_config.define_device(
        name="UNIX_LOCAL",
        device_class='moler.device.unixlocal.UnixLocal',
        connection_desc=None,
        connection_hops={}
    )
    device = device_factory.get_device(name='UNIX_LOCAL')

    assert device.__module__ == 'moler.device.unixlocal'
    assert device.__class__.__name__ == 'UnixLocal'


def test_cannot_select_named_device_without_connection(device_config, device_factory):
    device_config.define_device(
        name="UNIX_LOCAL",
        device_class='moler.device.unixlocal.UnixLocal',
        connection_desc=None,
        connection_hops={}
    )
    device_config.default_connection = None

    with pytest.raises(KeyError) as err:
        device_factory.get_device(name='UNIX_LOCAL')
    assert "No connection_desc selected (directly or via configuration)" in str(err.value)


def test_cannot_select_desc_device_without_connection(device_config, device_factory):
    device_config.default_connection = None

    with pytest.raises(KeyError) as err:
        device_factory.get_device(
            device_class='moler.device.unixlocal.UnixLocal',
            connection_hops={}
        )
    assert "No connection_desc selected (directly or via configuration)" in str(err.value)


def test_cannot_select_device_by_nonexisting_name(device_factory):
    """Non-existing means here not defined inside configuration"""
    with pytest.raises(KeyError) as err:
        device_factory.get_device(name='UNIX_LOCAL')
    assert "Device named 'UNIX_LOCAL' was not defined inside configuration" in str(err.value)


def test_load_config_and_load_new_devices(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    moler_config.load_config(config=conn_config, config_type='yaml')


def test_can_select_device_loaded_from_config_file(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    add_conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "added_device_config.yml")
    moler_config.load_config(config=conn_config, config_type='yaml')
    moler_config.load_config(config=add_conn_config, config_type='yaml')

    device = device_factory.get_device(name='UNIX_LOCAL')
    added_device = device_factory.get_device(name='ADDED_UNIX_LOCAL')
    for device in (device, added_device):
        assert device.__module__ == 'moler.device.unixlocal'
        assert device.__class__.__name__ == 'UnixLocal'


def test_can_clone_device(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    moler_config.load_config(config=conn_config, config_type='yaml')

    device_org_name = 'UNIX_LOCAL'
    device_cloned_name = 'CLONED_UNIX_LOCAL1'
    device_org = device_factory.get_device(name=device_org_name)
    assert device_org is not None
    device_cloned = device_factory.get_cloned_device(source_device=device_org, new_name=device_cloned_name)
    assert device_cloned is not None
    assert device_org != device_cloned
    assert device_org.io_connection != device_cloned.io_connection
    assert device_org.io_connection.moler_connection != device_cloned.io_connection.moler_connection
    assert device_org.io_connection.name != device_cloned.io_connection.name
    device_cached_cloned = device_factory.get_cloned_device(source_device=device_org, new_name=device_cloned_name)
    assert device_cloned == device_cached_cloned
    device_cached_cloned.goto_state('UNIX_LOCAL')


def test_close_defined_yaml_device(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    moler_config.load_config(config=conn_config, config_type='yaml')

    device_org_name = 'UNIX_LOCAL'
    device_org = device_factory.get_device(name=device_org_name)
    assert device_org is not None
    device_org.remove()
    with pytest.raises(KeyError):
        device_factory.get_device(name=device_org_name)

    moler_config.clear()
    device_factory._clear()

    moler_config.load_config(config=conn_config, config_type='yaml')
    device_2 = device_factory.get_device(name=device_org_name)
    assert device_2 != device_org


def test_load_devices_after_deletion(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")

    moler_config.load_config(config=conn_config)
    devices_loaded1 = device_factory.get_devices_by_type(None)
    device_org_name = 'UNIX_LOCAL'
    device_org = device_factory.get_device(name=device_org_name)
    assert device_org is not None

    device_factory.remove_all_devices()
    devices_removed = device_factory.get_devices_by_type(None)
    assert len(devices_removed) == 0
    with pytest.raises(KeyError):
        device_factory.get_device(name=device_org_name)

    moler_config.load_config(config=conn_config)
    devices_loaded2 = device_factory.get_devices_by_type(None)
    device_2 = device_factory.get_device(name=device_org_name)
    assert device_2 != device_org
    assert len(devices_loaded1) == len(devices_loaded2)


def test_remove_device_with_commands(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    moler_config.load_config(config=conn_config)

    device_org_name = 'UNIX_LOCAL'
    state = "UNIX_LOCAL"
    dev = device_factory.get_device(name=device_org_name)
    assert dev is not None
    dev.goto_state(state=state)
    cmd_who_ami = dev.get_cmd(cmd_name="whoami")
    result = cmd_who_ami()
    assert result is not None
    assert 'USER' in result
    user1 = result['USER']
    id_dev = id(dev)
    id_io = id(dev.io_connection)
    id_mc = id(dev.io_connection.moler_connection)
    device_factory.remove_all_devices()
    moler_config.load_config(config=conn_config)

    for _ in range(5):
        dev2 = device_factory.get_device(name=device_org_name)
        dev2.goto_state(state=state)
        cmd_who_ami2 = dev2.get_cmd(cmd_name="whoami")
        result2 = cmd_who_ami2()
        assert result2 is not None
        assert 'USER' in result2
        user2 = result2['USER']
        assert user1 == user2
        id_dev2 = id(dev2)
        id_io2 = id(dev2.io_connection)
        id_mc2 = id(dev2.io_connection.moler_connection)
        assert dev2.name != device_org_name
        assert dev2.public_name == device_org_name
        assert id_dev != id_dev2
        assert id_io != id_io2
        assert id_mc != id_mc2
        id_dev = id_dev2
        id_io = id_io2
        id_mc = id_mc2
        dev2.remove()


def test_can_remove_device_twice(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    moler_config.load_config(config=conn_config, config_type='yaml')

    device_org_name = 'UNIX_LOCAL'
    device_org = device_factory.get_device(name=device_org_name)
    assert device_org is not None
    device_org.remove()
    device_org.remove()


def test_clone_device_from_cloned_device(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    moler_config.load_config(config=conn_config, config_type='yaml')

    device_org_name = 'UNIX_LOCAL'
    device_cloned_name = 'UNIX_LOCAL_CLONED'
    device_recloned_name = 'UNIX_LOCAL_RECLONED'
    device_org = device_factory.get_device(name=device_org_name)
    assert device_org is not None
    device_cloned = device_factory.get_cloned_device(source_device=device_org, new_name=device_cloned_name)
    device_recloned = device_factory.get_cloned_device(source_device=device_cloned, new_name=device_recloned_name)
    assert device_cloned != device_recloned
    assert device_cloned != device_org
    assert device_recloned != device_org
    device_cloned.remove()
    device_recloned.remove()
    with pytest.raises(KeyError):
        device_factory.get_device(name=device_cloned_name)
    with pytest.raises(KeyError):
        device_factory.get_device(name=device_recloned_name)
    with pytest.raises(KeyError):  # Cannot clone forgotten device.
        device_factory.get_cloned_device(source_device=device_cloned_name, new_name=device_recloned_name)
    with pytest.raises(KeyError):  # Cannot clone even passed reference to forgotten device.
        device_factory.get_cloned_device(source_device=device_cloned, new_name=device_recloned_name)


def test_clone_and_remove_device(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    moler_config.load_config(config=conn_config, config_type='yaml')

    device_org_name = 'UNIX_LOCAL'
    device_cloned_name = 'CLONED_UNIX_LOCAL_TO_FORGET'
    device_org = device_factory.get_device(name=device_org_name)
    assert device_org is not None
    with pytest.raises(KeyError):
        device_factory.get_device(name=device_cloned_name)
    device_cloned = device_factory.get_cloned_device(source_device=device_org, new_name=device_cloned_name)
    assert device_cloned is not None
    device_cloned.goto_state('UNIX_LOCAL')
    cmd_ping = device_cloned.get_cmd(cmd_name="ping", cmd_params={"destination": 'localhost', "options": "-w 3"})
    cmd_ping.start()
    device_cloned.remove()
    with pytest.raises(WrongUsage) as err:
        cmd_ping.await_done()
    assert "is about to be closed" in str(err.value)
    with pytest.raises(KeyError):
        device_factory.get_device(name=device_cloned_name)
    # We can clone device with the same name again!
    device_cloned_again = device_factory.get_cloned_device(source_device=device_org, new_name=device_cloned_name)
    assert device_cloned != device_cloned_again
    device_by_alias = device_factory.get_device(name=device_cloned_again.public_name)
    assert device_by_alias == device_cloned_again
    assert device_cloned_again.name != device_cloned_name
    assert device_cloned_again.public_name == device_cloned_name
    cmd_ping = device_cloned_again.get_cmd(cmd_name="ping", cmd_params={"destination": 'localhost', "options": "-c 1"})
    cmd_ping()
    device_factory.remove_device(name=device_cloned_name)
    with pytest.raises(KeyError):
        device_factory.get_device(name=device_cloned_name)
    with pytest.raises(KeyError):
        device_factory.remove_device(name=device_cloned_name)


def test_can_clone_device_via_name(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    moler_config.load_config(config=conn_config, config_type='yaml')

    device_org_name = 'UNIX_LOCAL'
    device_cloned_name = 'CLONED_UNIX_LOCAL2'
    device_org = device_factory.get_device(name=device_org_name)
    assert device_org is not None
    device_cloned = device_factory.get_cloned_device(source_device=device_org_name, new_name=device_cloned_name)
    assert device_cloned is not None
    assert device_org != device_cloned
    assert device_org.io_connection != device_cloned.io_connection
    assert device_org.io_connection.moler_connection != device_cloned.io_connection.moler_connection
    assert device_org.io_connection.name != device_cloned.io_connection.name
    device_cached_cloned = device_factory.get_cloned_device(source_device=device_org, new_name=device_cloned_name)
    assert device_cloned == device_cached_cloned
    device_cached_cloned.goto_state('UNIX_LOCAL')


def test_can_clone_device_via_yaml(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    moler_config.load_config(config=conn_config, config_type='yaml')

    device_org_name = 'UNIX_LOCAL_TO_CLONE'
    device_cloned_name = 'UNIX_LOCAL_CLONED_VIA_YAML'
    device_org = device_factory.get_device(name=device_org_name)
    assert device_org is not None
    device_cloned = device_factory.get_device(name=device_cloned_name)
    assert device_cloned is not None
    assert type(device_org) is type(device_cloned)
    assert device_org != device_cloned
    assert device_org.io_connection != device_cloned.io_connection
    assert device_org.io_connection.moler_connection != device_cloned.io_connection.moler_connection
    assert device_org.io_connection.name != device_cloned.io_connection.name
    device_cached_cloned = device_factory.get_cloned_device(source_device=device_org, new_name=device_cloned_name)
    assert device_cloned == device_cached_cloned


def test_cannot_clone_device_the_same_name_different_sources(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    moler_config.load_config(config=conn_config, config_type='yaml')

    device_org_name = 'UNIX_LOCAL'
    device_org_name_remote = 'UNIX_REMOTE_PROXY_PC'
    device_cloned_name = 'CLONED_UNIX_LOCAL3'
    device_org = device_factory.get_device(name=device_org_name)
    device_org_remote = device_factory.get_device(name=device_org_name_remote, initial_state='UNIX_LOCAL')
    assert device_org is not None

    device_cloned = device_factory.get_cloned_device(source_device=device_org_name, new_name=device_cloned_name,
                                                     initial_state='UNIX_LOCAL')
    assert device_cloned is not None
    with pytest.raises(WrongUsage):
        device_factory.get_cloned_device(source_device=device_org_remote, new_name=device_cloned_name,
                                         initial_state='UNIX_LOCAL')


def test_can_select_all_devices_loaded_from_config_file(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    moler_config.load_config(config=conn_config, config_type='yaml')

    device_factory.create_all_devices()

    device = device_factory._devices["UNIX_LOCAL"]

    assert device.__module__ == 'moler.device.unixlocal'
    assert device.__class__.__name__ == 'UnixLocal'


def test_can_select_neighbour_devices_loaded_from_config_file_(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    moler_config.load_config(config=conn_config, config_type='yaml')

    device_factory.create_all_devices()
    unix_local = device_factory.get_device(name='UNIX_LOCAL', establish_connection=False)
    import moler.device.scpi
    import moler.device.unixlocal
    neighbours = unix_local.get_neighbour_devices(device_type=moler.device.scpi.Scpi)
    assert 1 == len(neighbours)
    assert isinstance(neighbours[0], moler.device.scpi.Scpi)
    assert unix_local in neighbours[0].get_neighbour_devices(device_type=None)
    assert unix_local in neighbours[0].get_neighbour_devices(device_type=moler.device.unixlocal.UnixLocal)
    assert unix_local in device_factory.get_devices_by_type(device_type=None)
    assert unix_local in device_factory.get_devices_by_type(device_type=moler.device.unixlocal.UnixLocal)
    unix_local.goto_state(state=unix_local.initial_state)


def test_can_select_device_loaded_from_env_variable(moler_config, monkeypatch, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    monkeypatch.setitem(os.environ, 'MOLER_CONFIG', conn_config)
    moler_config.load_config(from_env_var="MOLER_CONFIG", config_type='yaml')

    device = device_factory.get_device(name='UNIX_LOCAL')

    assert device.__module__ == 'moler.device.unixlocal'
    assert device.__class__.__name__ == 'UnixLocal'


def test_load_config_checks_env_variable_existence(moler_config):
    with pytest.raises(KeyError) as err:
        moler_config.load_config(from_env_var="MOLER_CONFIG", config_type='yaml')

    assert "Environment variable 'MOLER_CONFIG' is not set" in str(err.value)


def test_return_created_device_when_call_another_time_for_same_named_device(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    moler_config.load_config(config=conn_config, config_type='yaml')

    device = device_factory.get_device(name='UNIX_LOCAL')
    same_device = device_factory.get_device(name='UNIX_LOCAL')

    assert device.__module__ == 'moler.device.unixlocal'
    assert device.__class__.__name__ == 'UnixLocal'

    assert same_device.__module__ == 'moler.device.unixlocal'
    assert same_device.__class__.__name__ == 'UnixLocal'

    assert device == same_device


def test_log_error_when_not_abs_path_for_configuation_path_was_used(moler_config):
    from moler.exceptions import MolerException

    conn_config = os.path.join(os.pardir, "resources", "device_config.yml")
    with pytest.raises(MolerException) as err:
        moler_config.load_config(config=conn_config, config_type='yaml')

    assert "Loading configuration requires absolute path and not '../resources/device_config.yml'" in str(err.value)


def test_create_all_devices_not_existed_device(moler_config, device_factory):

    conn_config = {
        'LOGGER': {
            'PATH': '/tmp/',
            'RAW_LOG': True,
            'DATE_FORMAT': '%d %H:%M:%S'
        },
        'DEVICES': {
            'UNIX_LOCAL': {
                'DEVICE_CLASS': 'moler.device.unixlocal.UnixLocal',
                'INITIAL_STATE': 'UNIX_LOCAL',
            },
            'UNIX_LOCAL_NOT_EXISTED': {
                'DEVICE_CLASS': 'moler.device.notExistedClass',
                'INITIAL_STATE': 'UNIX_LOCAL',
            }
        }
    }
    moler_config.load_config(config=conn_config, config_type='dict')
    with pytest.raises(AttributeError) as err:
        device_factory.create_all_devices()
    device_factory.create_all_devices(ignore_exception=True)
    assert "has no attribute 'notExistedClass'" in str(err.value)


def test_log_error_when_the_same_prompts_in_more_then_one_state(moler_config, device_factory):
    from moler.exceptions import MolerException

    conn_config = {
        'LOGGER': {
            'PATH': '/tmp/',
            'RAW_LOG': True,
            'DATE_FORMAT': '%d %H:%M:%S'
        },
        'DEVICES': {
            'UNIX_LOCAL_THE_SAME_PROMPTS': {
                'DEVICE_CLASS': 'moler.device.unixlocal.UnixLocal',
                'INITIAL_STATE': 'UNIX_LOCAL',
                'CONNECTION_HOPS': {
                    "UNIX_LOCAL": {
                        "UNIX_LOCAL_ROOT": {
                            "command_params": {
                                "expected_prompt": "^moler_bash#"
                            }
                        }
                    }
                }
            }
        }
    }
    with pytest.raises(MolerException) as err:
        moler_config.load_config(config=conn_config, config_type='dict')
        device_factory.get_device(name='UNIX_LOCAL_THE_SAME_PROMPTS')

    assert "Incorrect device configuration. The same prompts for state" in str(err.value)


def test_return_new_device_when_call_another_time_same_desc_device(device_factory):
    device = device_factory.get_device(
        device_class='moler.device.unixlocal.UnixLocal',
        connection_desc={
            "io_type": "terminal",
            "variant": "threaded"
        },
        connection_hops={}
    )

    another_device = device_factory.get_device(
        device_class='moler.device.unixlocal.UnixLocal',
        connection_desc={
            "io_type": "terminal",
            "variant": "threaded"
        },
        connection_hops={}
    )

    assert device.__module__ == 'moler.device.unixlocal'
    assert device.__class__.__name__ == 'UnixLocal'

    assert another_device.__module__ == 'moler.device.unixlocal'
    assert another_device.__class__.__name__ == 'UnixLocal'

    assert device != another_device


def test_cannot_load_config_from_when_path_or_from_env_var_not_provide(moler_config):
    with pytest.raises(WrongUsage) as err:
        moler_config.load_config()

    assert "Provide either 'config' or 'from_env_var' parameter (none given)" in str(err.value)


@pytest.mark.parametrize('params', [{'config': (), 'config_type': "wrong_type"},  # test backward compatibility
                                    {'from_env_var': 'AAA', 'config': [1, 2]},
                                    {'config': ()}])
def test_cannot_load_config_from_when_wrong_config_type_provided(moler_config, params):
    with pytest.raises(WrongUsage) as err:
        moler_config.load_config(**params)

    assert "Unsupported config type" in str(err.value)


def test_can_select_device_loaded_from_config_dict(moler_config, device_factory):
    ConnectionObserver.get_unraised_exceptions(True)

    @MolerTest.raise_background_exceptions(check_steps_end=True)
    def can_select_device_loaded_from_config_dict(moler_config, device_factory):
        conn_config = {
            'LOGGER': {
                'PATH': '/tmp/',
                'RAW_LOG': True,
                'DATE_FORMAT': '%d %H:%M:%S'
            },
            'DEVICES': {
                'UNIX_LOCAL': {
                    'DEVICE_CLASS': 'moler.device.unixlocal.UnixLocal',
                    'INITIAL_STATE': 'UNIX_LOCAL'
                }
            }
        }
        moler_config.load_config(config=conn_config, config_type='dict')

        device = device_factory.get_device(name='UNIX_LOCAL')

        assert device.__module__ == 'moler.device.unixlocal'
        assert device.__class__.__name__ == 'UnixLocal'

        device.__del__()

        MolerTest.steps_end()
    can_select_device_loaded_from_config_dict(moler_config, device_factory)


def test_can_load_configuration_when_already_loaded_from_same_dict(moler_config, device_factory):
    conn_config = {
        'LOGGER': {
            'PATH': '/tmp/',
            'RAW_LOG': True,
            'DATE_FORMAT': '%d %H:%M:%S'
        },
        'DEVICES': {
            'UNIX_LOCAL': {
                'DEVICE_CLASS': 'moler.device.unixlocal.UnixLocal',
                'INITIAL_STATE': 'UNIX_LOCAL'
            }
        }
    }
    moler_config.load_config(config=conn_config, config_type='dict')
    devices1 = device_factory.get_devices_by_type(None)
    moler_config.load_config(config=conn_config, config_type='dict')
    devices2 = device_factory.get_devices_by_type(None)
    assert devices1 == devices2


def test_can_load_configuration_with_the_same_named_device_loaded_from_another_dict_the_same_params(moler_config,
                                                                                                    device_factory):

    conn_config = {
        'LOGGER': {
            'PATH': '/tmp/',
            'RAW_LOG': True,
            'DATE_FORMAT': '%d %H:%M:%S'
        },
        'DEVICES': {
            'UNIX_LOCAL': {
                'DEVICE_CLASS': 'moler.device.unixlocal.UnixLocal',
                'INITIAL_STATE': 'UNIX_LOCAL'
            }
        }
    }

    new_conn_config = {
        'LOGGER': {
            'PATH': '/tmp/different',
            'RAW_LOG': True,
            'DATE_FORMAT': '%d %H:%M:%S'
        },
        'DEVICES': {
            'UNIX_LOCAL': {
                'DEVICE_CLASS': 'moler.device.unixlocal.UnixLocal',
                'INITIAL_STATE': 'UNIX_LOCAL'
            }
        }
    }
    import moler.device.unixlocal
    moler_config.load_config(config=conn_config, config_type='dict')
    device1 = device_factory.get_device("UNIX_LOCAL")
    devices1 = device_factory.get_devices_by_type(moler.device.unixlocal.UnixLocal)
    moler_config.load_config(config=new_conn_config, config_type='dict')
    device2 = device_factory.get_device("UNIX_LOCAL")
    devices2 = device_factory.get_devices_by_type(moler.device.unixlocal.UnixLocal)
    assert device1 == device2
    assert devices1 == devices2


def test_cannot_load_configuration_with_the_same_named_device_loaded_from_another_dict_different_class(moler_config):

    conn_config = {
        'LOGGER': {
            'PATH': '/tmp/',
            'RAW_LOG': True,
            'DATE_FORMAT': '%d %H:%M:%S'
        },
        'DEVICES': {
            'UNIX_LOCAL': {
                'DEVICE_CLASS': 'moler.device.unixlocal.UnixLocal',
                'INITIAL_STATE': 'UNIX_LOCAL'
            }
        }
    }

    new_conn_config = {
        'LOGGER': {
            'PATH': '/tmp/',
            'RAW_LOG': True,
            'DATE_FORMAT': '%d %H:%M:%S'
        },
        'DEVICES': {
            'UNIX_LOCAL': {
                'DEVICE_CLASS': 'moler.device.unixremote.UnixRemote',
                'INITIAL_STATE': 'UNIX_REMOTE'
            }
        }
    }
    moler_config.load_config(config=conn_config, config_type='dict')
    with pytest.raises(WrongUsage) as err:
        moler_config.load_config(config=new_conn_config, config_type='dict')
    assert "and now requested as instance of class" in str(err.value)


def test_cannot_load_device_from_updated_dict_different_class(moler_config):

    conn_config = {
        'LOGGER': {
            'PATH': '/tmp/',
            'RAW_LOG': True,
            'DATE_FORMAT': '%d %H:%M:%S'
        },
        'DEVICES': {
            'UNIX_LOCAL': {
                'DEVICE_CLASS': 'moler.device.unixlocal.UnixLocal',
                'INITIAL_STATE': 'UNIX_LOCAL'
            }
        }
    }

    moler_config.load_config(config=conn_config, config_type='dict')

    conn_config['DEVICES']['UNIX_LOCAL']['DEVICE_CLASS'] = "moler.device.unixlocal.NiotExitedDevice"

    with pytest.raises(WrongUsage) as err:
        moler_config.load_config(config=conn_config, config_type='dict')
    assert "and now requested as instance of class" in str(err.value)


def test_cannot_load_configuration_with_the_same_named_device_loaded_from_another_dict_different_hops(moler_config):

    conn_config = {
        'LOGGER': {
            'PATH': '/tmp/',
            'RAW_LOG': True,
            'DATE_FORMAT': '%d %H:%M:%S'
        },
        'DEVICES': {
            'UNIX_LOCAL': {
                'DEVICE_CLASS': 'moler.device.unixlocal.UnixLocal',
                'INITIAL_STATE': 'UNIX_LOCAL'
            }
        }
    }

    new_conn_config = {
        'LOGGER': {
            'PATH': '/tmp/',
            'RAW_LOG': True,
            'DATE_FORMAT': '%d %H:%M:%S'
        },
        'DEVICES': {
            'UNIX_LOCAL': {
                'DEVICE_CLASS': 'moler.device.unixlocal.UnixLocal',
                'CONNECTION_HOPS': {
                    'UNIX_LOCAL': {
                        'UNIX_LOCAL_ROOT': {
                            "command_params": {
                                "password": "root_password",
                                "expected_prompt": r'local_root_prompt',
                            }
                        }
                    }
                }
            }
        }
    }
    moler_config.load_config(config=conn_config, config_type='dict')
    with pytest.raises(WrongUsage) as err:
        moler_config.load_config(config=new_conn_config, config_type='dict')
    assert "but now requested with SM params" in str(err.value)


class UnixLocalWithExtraParam(UnixLocal):
    def __init__(self, sm_params=None, name=None, io_connection=None, io_type=None, variant=None,
                 io_constructor_kwargs=None, initial_state=None, lazy_cmds_events=False, extra_param_name=None,
                 extra_param2=None):
        super(UnixLocalWithExtraParam, self).__init__(sm_params=sm_params, name=name, io_connection=io_connection,
                                                      io_type=io_type, variant=variant,
                                                      io_constructor_kwargs=io_constructor_kwargs,
                                                      initial_state=initial_state,
                                                      lazy_cmds_events=lazy_cmds_events)
        self.extra_value = extra_param_name
        self.extra_value2 = extra_param2


def test_load_device_from_config_extra_param(moler_config, device_factory):

    config1 = {
        'LOGGER': {
            'PATH': '/tmp/',
            'RAW_LOG': True,
            'DATE_FORMAT': '%d %H:%M:%S'
        },
        'DEVICES': {
            'UNIX_LOCAL': {
                'DEVICE_CLASS': 'test.device.test_device_configuration.UnixLocalWithExtraParam',
                'INITIAL_STATE': 'UNIX_LOCAL',
                'ADDITIONAL_PARAMS': {
                    'extra_param_name': r"value for extra param",
                    'extra_param2': r'great value'
                },
            }
        }
    }

    moler_config.load_config(config1, None, 'dict')
    dev1 = device_factory.get_device("UNIX_LOCAL")
    assert dev1.extra_value == r"value for extra param"
    assert dev1.extra_value2 == r'great value'


def test_load_device_from_config(moler_config, device_factory):
    config1 = {
        'LOGGER': {
            'PATH': '/tmp/',
            'RAW_LOG': True,
            'DATE_FORMAT': '%d %H:%M:%S'
        },
        'DEVICES': {
            'UNIX_LOCAL': {
                'DEVICE_CLASS': 'moler.device.unixlocal.UnixLocal',
                'INITIAL_STATE': 'UNIX_LOCAL'
            }
        }
    }
    config2 = {
        'LOGGER': {
            'PATH': '/tmp/',
            'RAW_LOG': True,
            'DATE_FORMAT': '%d %H:%M:%S'
        },
        'DEVICES': {
            'UNIX_LOCAL2': {
                'DEVICE_CLASS': 'moler.device.unixlocal.UnixLocal',
                'INITIAL_STATE': 'UNIX_LOCAL'
            }
        }
    }
    moler_config.load_config(config1, None, 'dict')
    dev1_prev = device_factory.get_device("UNIX_LOCAL")
    with pytest.raises(KeyError):
        device_factory.get_device("UNIX_LOCAL2")

    moler_config.load_device_from_config(config2)
    dev = device_factory.get_device('UNIX_LOCAL2')
    assert dev is not None
    dev1_after = device_factory.get_device('UNIX_LOCAL')
    assert dev1_prev == dev1_after


def test_create_device_without_hops():
    connection_desc = {
        "io_type": "terminal",
        "variant": "threaded"
    }
    dev = DeviceFactory.get_device(connection_desc=connection_desc, device_class='moler.device.unixlocal.UnixLocal',
                                   connection_hops=dict())
    assert dev is not None


def test_can_load_configuration_when_already_loaded_from_same_file(moler_config, device_factory):
    conn_config = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "device_config.yml")
    moler_config.load_config(config=conn_config, config_type='yaml')
    moler_config.load_config(config=conn_config, config_type='yaml')


# --------------------------- resources ---------------------------


@pytest.fixture
def moler_config(clear_all_cfg):
    import moler.config as moler_cfg
    yield moler_cfg


@pytest.fixture
def device_config(clear_all_cfg):
    import moler.config.devices as dev_cfg
    yield dev_cfg


@pytest.fixture
def device_factory(clear_all_cfg):
    from moler.device.device import DeviceFactory as dev_factory
    yield dev_factory


@pytest.fixture
def clear_all_cfg():
    import mock
    import moler.config as moler_cfg
    import moler.config.connections as conn_cfg
    import moler.config.devices as dev_cfg
    from moler.device.device import DeviceFactory as dev_factory

    empty_loaded_config = ["NOT_LOADED_YET"]
    default_connection = {"io_type": "terminal", "variant": "threaded"}

    with mock.patch.object(conn_cfg, "default_variant", {}):
        with mock.patch.object(conn_cfg, "named_connections", {}):
            with mock.patch.object(moler_cfg, "loaded_config", empty_loaded_config):
                with mock.patch.object(dev_cfg, "named_devices", {}):
                    with mock.patch.object(dev_cfg, "default_connection", default_connection):
                        with mock.patch.object(dev_factory, "_devices", {}):
                            with mock.patch.object(dev_factory, "_devices_params", {}):
                                with mock.patch.object(dev_factory, "_unique_names", {}):
                                    with mock.patch.object(dev_factory, "_already_used_names", set()):
                                        with mock.patch.object(dev_factory, "_was_any_device_deleted", False):
                                            yield conn_cfg
