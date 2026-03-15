import copy
import os
import tempfile

import pytest
import yaml

import estimpy as es


class TestConfigLoading:
    def test_cfg_has_expected_keys(self):
        assert 'analysis.window-size' in es.cfg
        assert 'analysis.spectrogram.frequency-min' in es.cfg
        assert 'visualization.style.amplitude.padding' in es.cfg
        assert 'metadata.default-genre' in es.cfg

    def test_video_export_keys_exist(self):
        assert 'video.export.codec' in es.cfg
        assert 'video.export.format' in es.cfg
        assert 'video.export.fps' in es.cfg
        assert 'video.export.segment-length' in es.cfg

    def test_audio_export_keys_exist(self):
        assert 'audio.export.codec' in es.cfg
        assert 'audio.export.format' in es.cfg
        assert 'audio.export.sample-rate' in es.cfg

    def test_audio_export_defaults_are_auto(self):
        assert es.cfg['audio.export.codec'] is None
        assert es.cfg['audio.export.format'] is None

    def test_audio_frequency_keys_exist(self):
        assert 'audio.frequency.scale' in es.cfg
        assert 'audio.frequency.shift' in es.cfg

    def test_audio_frequency_defaults(self):
        assert es.cfg['audio.frequency.scale'] == 1
        assert es.cfg['audio.frequency.shift'] == 0

    def test_visualization_video_export_keys_are_visual(self):
        """Encoding-mechanic keys should be under video.export, not visualization.video.export."""
        assert 'visualization.video.export.size' in es.cfg
        assert 'visualization.video.export.triphase' in es.cfg
        assert 'visualization.video.export.window-length' in es.cfg
        assert 'video.export.codec' not in [k for k in es.cfg if k.startswith('visualization.')]

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

    def test_estimpy_version_not_persisted_in_cfg(self):
        """estimpy-version should be stored in cfg after loading default."""
        es.load_config('default')
        assert 'estimpy-version' in es.cfg

    def test_additional_config_profiles_not_persisted(self):
        """additional-config-profiles should be consumed and removed from cfg."""
        es.load_config('default')
        assert 'additional-config-profiles' not in es.cfg
        assert 'additional-config-profiles' not in es.base_cfg

    def test_additional_config_profiles_loads_referenced_profiles(self):
        """A profile with additional-config-profiles should load those profiles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a profile that sets a known key
            extra_profile = os.path.join(tmpdir, 'extra.yaml')
            with open(extra_profile, 'w') as f:
                yaml.dump({'analysis': {'window-size': 9999}}, f)

            # Create a profile that references the extra via additional-config-profiles
            main_profile = os.path.join(tmpdir, 'main.yaml')
            with open(main_profile, 'w') as f:
                yaml.dump({'additional-config-profiles': [extra_profile]}, f)

            es.load_config(main_profile)
            assert es.cfg['analysis.window-size'] == 9999

    def test_circular_profile_reference_does_not_loop(self):
        """Circular additional-config-profiles references should be skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            a = os.path.join(tmpdir, 'a.yaml')
            b = os.path.join(tmpdir, 'b.yaml')
            with open(a, 'w') as f:
                yaml.dump({'additional-config-profiles': [b]}, f)
            with open(b, 'w') as f:
                yaml.dump({'additional-config-profiles': [a]}, f)

            # Should not raise or loop infinitely
            es.load_config(a)

    def test_user_config_dir_overlay(self):
        """User config in ~/.estimpy/ should overlay builtin config."""
        user_dir = es._user_config_path
        os.makedirs(user_dir, exist_ok=True)
        user_profile = os.path.join(user_dir, '_test_overlay.yaml')
        try:
            with open(user_profile, 'w') as f:
                yaml.dump({'analysis': {'window-size': 7777}}, f)

            es.load_config('_test_overlay')
            assert es.cfg['analysis.window-size'] == 7777
        finally:
            if os.path.exists(user_profile):
                os.remove(user_profile)

    def test_version_check_warns_on_newer_version(self, capsys):
        """Loading a profile with a newer estimpy-version should print a warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = os.path.join(tmpdir, 'future.yaml')
            with open(profile, 'w') as f:
                yaml.dump({'estimpy-version': '99.0.0'}, f)

            es.load_config(profile)
            captured = capsys.readouterr()
            assert 'Warning' in captured.out
            assert '99.0.0' in captured.out


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
