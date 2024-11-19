import abc
import enum
import os
import re
import tempfile
import typing

import estimpy as es
import mutagen.id3
import mutagen.mp4


class MetadataFileFormats(enum.StrEnum):
    M4A = 'm4a'
    MP3 = 'mp3'
    MP4 = 'mp4'


class MetadataImage:
    def __init__(self, image_data: bytes = None, mime_type: str = None):
        self.image_data = image_data
        self.mime_type = mime_type if mime_type else self.image_data_to_mime_type(image_data)

    @classmethod
    def format_to_mime_type(cls, format: str):
        if not format:
            return ''

        format = 'jpeg' if format == 'jpg' else format

        return f'image/{format}'

    @classmethod
    def image_data_to_format(cls, image_data: bytes):
        if not image_data or len(image_data) < 8:
            return None
        elif image_data[:3] == b'\xff\xd8\xff':
            return 'jpeg'
        elif image_data[:8] == b'\x89PNG\r\n\x1a\n':
            return 'png'
        else:
            return None

    @classmethod
    def image_data_to_mime_type(cls, image_data: bytes):
        return cls.format_to_mime_type(cls.image_data_to_format(image_data))


class Metadata:
    def __init__(self, file: str = None, metadata: dict = None):
        self._data = {}  # type: dict
        self._file = None
        self._format = None

        self.clear()
        self.set_file(file)
        self.load()
        self.set_metadata(metadata)

    @property
    def file(self) -> str:
        return self._file

    @file.setter
    def file(self, value):
        self.set_file(value)

    @property
    def format(self) -> str:
        return self._format

    # Getters and setters for tags

    # album
    @property
    def album(self) -> str:
        return self.get_tag('album')

    @album.setter
    def album(self, value):
        self.set_tag('album', value)

    # artist
    @property
    def artist(self) -> str:
        return self.get_tag('artist')

    @artist.setter
    def artist(self, value):
        self.set_tag('artist', value)

    # genre
    @property
    def genre(self) -> str:
        return self.get_tag('genre')

    @genre.setter
    def genre(self, value):
        self.set_tag('genre', value)

    # image
    @property
    def image(self) -> MetadataImage | None:
        return self.get_tag('image')

    @image.setter
    def image(self, value):
        self.set_tag('image', value)

    # title
    @property
    def title(self) -> str:
        return self.get_tag('title')

    @title.setter
    def title(self, value):
        self.set_tag('title', value)

    def clear(self):
        self._data = {
            'album': None,
            'artist': None,
            'genre': es.cfg['metadata.default-genre'],
            'image': None,
            'title': None
        }

    def get_metadata(self) -> dict:
        return self._data

    def get_tag(self, tag: str) -> typing.Any:
        return self._data[tag] if tag in self._data else None

    def load(self) -> None:
        if self.file is None or not os.path.isfile(self.file):
            return

        # Parse file name to look for tag fields
        file_name_metadata = self._get_metadata_from_file_path(self.file)

        for tag, value in file_name_metadata.items():
            if tag in self._data:
                self.set_tag(tag, value)

        # Read tag data from file if it exists.
        # These values take precedence if overlapping fields from file name matching.
        metadata = {}
        if self._format == MetadataFileFormats.MP3:
            metadata = MetadataFormatMP3.load(self.file)
        elif self._format == MetadataFileFormats.M4A or self._format == MetadataFileFormats.MP4:
            metadata = MetadataFormatMP4.load(self.file)

        self.set_metadata(metadata)

    def set_file(self, file: str = None):
        self._file = file

        if file:
            file_extension = os.path.splitext(self.file)[1]
            self._format = file_extension[1:].lower() if file_extension else None

    def save(self):
        if self.file is None:
            raise Exception('No filename specified')
        elif self._format not in MetadataFileFormats._value2member_map_:
            raise Exception('Unsupported file format')
        elif self._format == MetadataFileFormats.MP3:
            MetadataFormatMP3.save(self.file, self._data)
        elif self._format == MetadataFileFormats.M4A or self._format == MetadataFileFormats.MP4:
            MetadataFormatMP4.save(self.file, self._data)

    def set_tag(self, tag: str, value=None, overwrite: bool = True):
        if tag in self._data and (overwrite or not self.get_tag(tag)):
            if tag == 'image':
                if not isinstance(value, MetadataImage):
                    value = MetadataImage(image_data=value)

            self._data[tag] = value

    def set_metadata(self, metadata: dict = None, overwrite: bool = True) -> None:
        if metadata is None:
            return

        for tag in self._data.keys():
            if tag in metadata and (overwrite or not self.get_tag(tag)):
                self.set_tag(tag, metadata[tag])

    def _get_metadata_from_file_path(self, file: str) -> dict:
        metadata = {}

        if not os.path.isfile(file):
            return metadata

        # Get the full absolute file path without the extension in case it's useful to match against directory names
        file_path, _ = os.path.splitext(os.path.abspath(file))

        # Use regular expressions to parse the pattern and extract metadata fields
        regex = es.cfg['metadata.file-path-pattern']
        matches = re.search(regex, file_path)

        if matches is not None:
            return matches.groupdict()
        else:
            # Fallback plan is to just treat the whole title of the file (without the extension) as the title
            return {'title': os.path.splitext(file)[0]}


class MetadataFormat(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def _tag_fields(cls) -> dict:
        pass

    @classmethod
    def load(cls, file: str) -> dict:
        tags = {}
        file_tags = cls._load_file_tags(file)

        if not file_tags:
            return {}

        for tag, file_tag_field in cls._tag_fields().items():
            if file_tag_field in file_tags and file_tags[file_tag_field][0]:
                tags[tag] = file_tags[file_tag_field][0]

        image = cls._get_metadata_image(file_tags)

        if image:
            tags['image'] = image

        return tags

    @classmethod
    def save(cls, file: str, metadata: dict):
        file_tags = cls._load_file_tags(file)

        if not file_tags:
            return

        for tag, value in metadata.items():
            cls._set_file_tag_value(file_tags=file_tags, tag=tag, value=value)

        file_tags.save()

        return

    @classmethod
    @abc.abstractmethod
    def _get_metadata_image(cls, file_tags) -> MetadataImage | None:
        pass

    @classmethod
    @abc.abstractmethod
    def _load_file_tags(cls, file: str):
        pass

    @classmethod
    @abc.abstractmethod
    def _set_file_tag_value(cls, file_tags, tag: str, value) -> MetadataImage | None:
        pass


class MetadataFormatMP3(MetadataFormat, abc.ABC):
    @classmethod
    def _tag_fields(cls) -> dict:
        return {
            'album': 'TALB',
            'artist': 'TPE1',
            'genre': 'TCON',
            'title': 'TIT2'
        }

    @classmethod
    def _get_metadata_image(cls, file_tags: mutagen.id3.ID3) -> MetadataImage | None:
        image = None

        image_tag_field = 'APIC:'
        if image_tag_field in file_tags:
            image = MetadataImage(image_data=file_tags[image_tag_field].data, mime_type=file_tags[image_tag_field].mime)

        return image

    @classmethod
    def _load_file_tags(cls, file: str) -> mutagen.id3.ID3:
        return mutagen.id3.ID3(file)

    @classmethod
    def _set_file_tag_value(cls, file_tags: mutagen.id3.ID3, tag: str, value):
        if tag == 'image':
            file_tags.delall('APIC')
            if isinstance(value, MetadataImage) and value.image_data is not None:
                file_tags.add(
                    mutagen.id3.APIC(
                        data=value.image_data,
                        type=mutagen.id3.PictureType.COVER_FRONT,
                        desc='cover',
                        mime=value.mime_type))
        elif tag in cls._tag_fields():
            file_tag_field = cls._tag_fields()[tag]
            file_tags.delall(file_tag_field)

            if value is not None:
                file_tag_field_class = getattr(mutagen.id3, file_tag_field)
                file_tags[file_tag_field] = file_tag_field_class(encoding=3, text=U'' + str(value))

class MetadataFormatMP4(MetadataFormat, abc.ABC):
    @classmethod
    def _tag_fields(cls) -> dict:
        return {
            'album': '\xa9alb',
            'artist': '\xa9ART',
            'genre': '\xa9gen',
            'title': '\xa9nam2'
        }

    @classmethod
    def _get_metadata_image(cls, file_tags) -> MetadataImage | None:
        image = None

        image_tag_field = 'covr'
        if image_tag_field in file_tags:
            image = MetadataImage(image_data=file_tags[image_tag_field][0])

        return image

    @classmethod
    def _load_file_tags(cls, file: str) -> mutagen.mp4.MP4:
        return mutagen.mp4.MP4(file)

    @classmethod
    def _set_file_tag_value(cls, file_tags: mutagen.mp4.MP4, tag: str, value):
        if value is None:
            return

        if tag == 'image':
            if isinstance(value, MetadataImage) and value.image_data is not None:
                file_tags['covr'] = [mutagen.mp4.MP4Cover(value.image_data)]
        elif tag in cls._tag_fields():
            file_tag_field = cls._tag_fields()[tag]

            if file_tag_field in file_tags:
                del file_tags[file_tag_field]

            if value is not None:
                file_tags[file_tag_field] = value


def write_metadata(es_audio, image_file: str = None):
    # If image_file is specified, assume that is the file name to a freshly-generated image file
    if image_file is None:
        image_file = es.export.write_image(es_audio=es_audio, output_path=tempfile.gettempdir())
        es.utils.add_temp_file(image_file)

    image_data = open(image_file, 'rb').read()
    es_audio.metadata.image = image_data
    es_audio.metadata.save()

    es.utils.delete_temp_files()