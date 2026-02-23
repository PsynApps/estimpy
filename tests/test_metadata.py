import pytest

from estimpy.metadata import Metadata, MetadataImage


class TestMetadataFromDict:
    def test_init_with_dict(self):
        md = Metadata(metadata={'artist': 'TestArtist', 'title': 'TestTitle'})
        assert md.artist == 'TestArtist'
        assert md.title == 'TestTitle'

    def test_default_genre(self):
        md = Metadata()
        # genre should have a default value from config
        assert md.genre is not None


class TestMetadataGetSetTag:
    def test_set_and_get(self):
        md = Metadata()
        md.set_tag('artist', 'NewArtist')
        assert md.get_tag('artist') == 'NewArtist'

    def test_set_title_via_property(self):
        md = Metadata()
        md.title = 'MyTitle'
        assert md.title == 'MyTitle'

    def test_get_unknown_tag_returns_none(self):
        md = Metadata()
        assert md.get_tag('nonexistent_tag') is None


class TestMetadataClear:
    def test_clear_resets_tags(self):
        md = Metadata(metadata={'artist': 'Test', 'title': 'Song'})
        md.clear()
        assert md.artist is None
        assert md.title is None

    def test_clear_preserves_default_genre(self):
        md = Metadata()
        md.clear()
        assert md.genre is not None


class TestMetadataOverwrite:
    def test_overwrite_true_replaces(self):
        md = Metadata(metadata={'artist': 'Original'})
        md.set_tag('artist', 'Updated', overwrite=True)
        assert md.artist == 'Updated'

    def test_overwrite_false_preserves_existing(self):
        md = Metadata(metadata={'artist': 'Original'})
        md.set_tag('artist', 'Updated', overwrite=False)
        assert md.artist == 'Original'

    def test_overwrite_false_fills_empty(self):
        md = Metadata()
        md.set_tag('artist', 'New', overwrite=False)
        assert md.artist == 'New'


class TestSetMetadata:
    def test_set_multiple_tags(self):
        md = Metadata()
        md.set_metadata({'artist': 'A', 'title': 'T', 'album': 'AL'})
        assert md.artist == 'A'
        assert md.title == 'T'
        assert md.album == 'AL'

    def test_set_metadata_none_is_noop(self):
        md = Metadata(metadata={'artist': 'Keep'})
        md.set_metadata(None)
        assert md.artist == 'Keep'


class TestMetadataImage:
    def test_jpeg_detection(self):
        jpeg_header = b'\xff\xd8\xff\xe0' + b'\x00' * 100
        fmt = MetadataImage.image_data_to_format(jpeg_header)
        assert fmt == 'jpeg'

    def test_png_detection(self):
        png_header = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        fmt = MetadataImage.image_data_to_format(png_header)
        assert fmt == 'png'

    def test_unknown_format(self):
        assert MetadataImage.image_data_to_format(b'\x00\x00\x00\x00\x00\x00\x00\x00') is None

    def test_empty_data(self):
        assert MetadataImage.image_data_to_format(None) is None
        assert MetadataImage.image_data_to_format(b'') is None

    def test_format_to_mime_type(self):
        assert MetadataImage.format_to_mime_type('png') == 'image/png'
        assert MetadataImage.format_to_mime_type('jpeg') == 'image/jpeg'
        assert MetadataImage.format_to_mime_type('jpg') == 'image/jpeg'

    def test_mime_type_from_data(self):
        jpeg_data = b'\xff\xd8\xff\xe0' + b'\x00' * 100
        mime = MetadataImage.image_data_to_mime_type(jpeg_data)
        assert mime == 'image/jpeg'

    def test_image_init_auto_mime(self):
        png_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        img = MetadataImage(image_data=png_data)
        assert img.mime_type == 'image/png'
        assert img.image_data == png_data
