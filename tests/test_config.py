import copy
import os

import pytest

import estimpy as es


class TestConfigLoading:
    def test_cfg_has_expected_keys(self):
        assert 'analysis.window-size' in es.cfg
        assert 'analysis.spectrogram.frequency-min' in es.cfg
        assert 'visualization.style.amplitude.padding' in es.cfg
        assert 'metadata.default-genre' in es.cfg

    def test_base_cfg_has_expected_keys(self):
        assert 'analysis.window-size' in es.base_cfg
        assert 'metadata.default-genre' in es.base_cfg

    def test_load_config_profile(self):
        original_value = es.cfg.get('analysis.window-size')
        # Load a known profile that overrides some values
        config_dir = os.path.join(os.path.dirname(es.__file__), 'config')
        profiles = [f for f in os.listdir(config_dir) if f.endswith('.yaml') and f != 'default.yaml']
        if profiles:
            es.load_config(profiles[0])
            # Config should still have the key (may or may not have changed)
            assert 'analysis.window-size' in es.cfg

    def test_load_config_by_name_without_extension(self):
        # Should resolve 'default' to default.yaml in config dir
        es.load_config('default')
        assert 'analysis.window-size' in es.cfg

    def test_load_config_nonexistent_raises(self):
        with pytest.raises(Exception, match='does not exist'):
            es.load_config('nonexistent_profile_xyz')


class TestConfigUpdate:
    def test_update_bool_true(self):
        key = 'analysis.spectrogram.reassign'
        es.cfg[key] = False
        es.update_config_values({key: 'true'})
        assert es.cfg[key] is True

    def test_update_bool_false(self):
        key = 'analysis.spectrogram.reassign'
        es.cfg[key] = True
        es.update_config_values({key: 'false'})
        assert es.cfg[key] is False

    def test_update_bool_numeric(self):
        key = 'analysis.spectrogram.reassign'
        es.update_config_values({key: '1'})
        assert es.cfg[key] is True
        es.update_config_values({key: '0'})
        assert es.cfg[key] is False

    def test_update_int(self):
        key = 'analysis.window-size'
        es.update_config_values({key: '4096'})
        assert es.cfg[key] == 4096

    def test_update_float(self):
        key = 'analysis.spectrogram.reassign-smoothing'
        es.update_config_values({key: '2.5'})
        assert es.cfg[key] == 2.5

    def test_update_none_string(self):
        key = 'analysis.spectrogram.frequency-max'
        es.update_config_values({key: 'none'})
        assert es.cfg[key] is None

    def test_update_tilde_none(self):
        key = 'analysis.spectrogram.frequency-max'
        es.update_config_values({key: '~'})
        assert es.cfg[key] is None

    def test_update_invalid_key_raises(self):
        with pytest.raises(Exception, match='not valid'):
            es.update_config_values({'nonexistent.key.xyz': 'value'})

    def test_base_cfg_unchanged_after_update(self):
        key = 'analysis.window-size'
        original_base = es.base_cfg.get(key)
        es.update_config_values({key: '8192'})
        assert es.base_cfg.get(key) == original_base


class TestEventSystem:
    def test_listener_fires_on_trigger(self):
        called = []
        es.add_event_listener('test.event', lambda: called.append(True))
        es.trigger_event('test.event')
        assert len(called) == 1

    def test_multiple_listeners(self):
        results = []
        es.add_event_listener('test.multi', lambda: results.append('a'))
        es.add_event_listener('test.multi', lambda: results.append('b'))
        es.trigger_event('test.multi')
        assert results == ['a', 'b']

    def test_trigger_nonexistent_event_no_error(self):
        es.trigger_event('test.nonexistent.event.xyz')

    def test_config_updated_fires_on_load(self):
        called = []
        es.add_event_listener('config.updated', lambda: called.append(True))
        es.load_config('default')
        assert len(called) >= 1


class TestFlatDict:
    def test_simple_nesting(self):
        result = es._flat_dict({'a': {'b': 1, 'c': 2}})
        assert result == {'a.b': 1, 'a.c': 2}

    def test_deep_nesting(self):
        result = es._flat_dict({'a': {'b': {'c': 3}}})
        assert result == {'a.b.c': 3}

    def test_empty_dict(self):
        result = es._flat_dict({})
        assert result == {}

    def test_no_nesting(self):
        result = es._flat_dict({'x': 1, 'y': 2})
        assert result == {'x': 1, 'y': 2}
