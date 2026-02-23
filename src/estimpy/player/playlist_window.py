"""Playlist window for the EstimPy player."""
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QAbstractItemView, QFileDialog
)

import estimpy as es

AUDIO_FILE_FILTER = 'Audio Files (*.mp3 *.m4a *.mp4 *.wav *.flac *.ogg *.aac *.wma);;All Files (*)'
M3U_FILE_FILTER = 'M3U Playlist (*.m3u);;All Files (*)'


def _get_display_name(file_path):
    """Get a friendly display name for an audio file using metadata."""
    try:
        meta = es.metadata.Metadata(file=file_path)
        if meta.title:
            if meta.artist:
                return f'{meta.artist} - {meta.title}'
            return meta.title
    except Exception:
        pass

    return os.path.splitext(os.path.basename(file_path))[0]


def _parse_m3u(file_path):
    """Parse an M3U playlist file and return a list of validated absolute paths."""
    m3u_dir = os.path.dirname(os.path.abspath(file_path))
    paths = []

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Resolve relative paths against the M3U file's directory
            if not os.path.isabs(line):
                line = os.path.join(m3u_dir, line)

            line = os.path.normpath(line)

            if os.path.isfile(line):
                paths.append(line)
            else:
                print(f'Warning: File not found, skipping: {line}')

    return paths


def _write_m3u(file_path, audio_files):
    """Write an Extended M3U playlist file."""
    m3u_dir = os.path.dirname(os.path.abspath(file_path))

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')

        for audio_path in audio_files:
            display_name = _get_display_name(audio_path)

            # Try to compute a relative path
            try:
                rel = os.path.relpath(audio_path, m3u_dir)
                if rel.startswith('..'):
                    write_path = os.path.abspath(audio_path)
                else:
                    write_path = rel
            except ValueError:
                # On Windows, relpath can fail across drives
                write_path = os.path.abspath(audio_path)

            f.write(f'#EXTINF:-1,{display_name}\n')
            f.write(f'{write_path}\n')


class PlaylistListWidget(QListWidget):
    """QListWidget subclass that tracks drag-and-drop reorder operations."""

    def __init__(self, playlist_window):
        super().__init__()
        self._playlist_window = playlist_window

    def dropEvent(self, event):
        # Determine the source row before the drop
        dragged_item = self.currentItem()
        from_index = self.row(dragged_item) if dragged_item else -1

        # Let Qt handle the actual move
        super().dropEvent(event)

        # Determine the destination row after the drop
        if dragged_item and from_index >= 0:
            to_index = self.row(dragged_item)
            if from_index != to_index:
                self._playlist_window._on_reorder(from_index, to_index)


class PlaylistWindow(QDialog):
    """Non-modal dialog showing the current playlist with management controls."""

    def __init__(self, player_window):
        super().__init__(player_window)
        self._player_window = player_window
        self._player = player_window._player
        self._current_file_index = self._player.get_current_file_index()

        self.setWindowTitle('Playlist')
        self.setMinimumSize(350, 300)
        self.resize(400, 450)

        self._setup_ui()
        self._setup_dark_theme()

        # Populate the list
        self.set_files(self._player.get_audio_files())
        self.set_current_file(self._current_file_index)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # List widget with drag-and-drop reorder
        self._list = PlaylistListWidget(self)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        self._list.itemSelectionChanged.connect(self._update_button_states)
        layout.addWidget(self._list, stretch=1)

        # Button row
        button_row = QHBoxLayout()
        button_row.setSpacing(4)

        self._btn_add = QPushButton('Add')
        self._btn_add.setToolTip('Add files to playlist')
        self._btn_add.clicked.connect(self._on_add)
        self._btn_add.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button_row.addWidget(self._btn_add)

        self._btn_remove = QPushButton('Remove')
        self._btn_remove.setToolTip('Remove selected file from playlist')
        self._btn_remove.clicked.connect(self._on_remove)
        self._btn_remove.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_remove.setEnabled(False)
        button_row.addWidget(self._btn_remove)

        button_row.addStretch(1)

        self._btn_load = QPushButton('Load')
        self._btn_load.setToolTip('Load playlist from .m3u file')
        self._btn_load.clicked.connect(self._on_load)
        self._btn_load.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button_row.addWidget(self._btn_load)

        self._btn_save = QPushButton('Save')
        self._btn_save.setToolTip('Save playlist to .m3u file')
        self._btn_save.clicked.connect(self._on_save)
        self._btn_save.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button_row.addWidget(self._btn_save)

        layout.addLayout(button_row)

    def _setup_dark_theme(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
                color: #cccccc;
            }
            QListWidget {
                background-color: #2a2a2a;
                color: #cccccc;
                border: 1px solid #444;
                border-radius: 4px;
                font-size: 13px;
                outline: none;
            }
            QListWidget::item {
                padding: 4px 6px;
                border-bottom: 1px solid #333;
            }
            QListWidget::item:selected {
                background-color: #3a3a5a;
            }
            QListWidget::item:hover {
                background-color: #333;
            }
            QPushButton {
                background-color: #2a2a2a;
                color: #cccccc;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
            QPushButton:pressed {
                background-color: #4a4a4a;
            }
            QPushButton:disabled {
                color: #666;
                background-color: #222;
                border-color: #333;
            }
        """)

    # --- Public methods ---

    def set_files(self, file_paths):
        """Rebuild the list widget from a list of file paths."""
        self._list.clear()
        for path in file_paths:
            item = QListWidgetItem(_get_display_name(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self._list.addItem(item)

        self._update_button_states()

    def set_current_file(self, index):
        """Update the playing indicator to the given index."""
        old_index = self._current_file_index
        self._current_file_index = index

        # Clear old indicator
        if 0 <= old_index < self._list.count():
            item = self._list.item(old_index)
            text = item.text()
            if text.startswith('\u25b6 '):
                item.setText(text[2:])
            font = item.font()
            font.setBold(False)
            item.setFont(font)

        # Set new indicator
        if 0 <= index < self._list.count():
            item = self._list.item(index)
            text = item.text()
            if not text.startswith('\u25b6 '):
                item.setText(f'\u25b6 {text}')
            font = item.font()
            font.setBold(True)
            item.setFont(font)

        self._update_button_states()

    # --- Event handlers ---

    def _on_double_click(self, item):
        """Switch playback to the double-clicked file."""
        index = self._list.row(item)
        if index != self._current_file_index:
            self._player.set_audio(file_index=index)

    def _on_reorder(self, from_index, to_index):
        """Handle a drag-and-drop reorder within the list."""
        self._player.reorder_file(from_index, to_index)
        self._current_file_index = self._player.get_current_file_index()

        # Refresh the playing indicator (items moved, so re-apply bold/▶)
        for i in range(self._list.count()):
            item = self._list.item(i)
            text = item.text()
            if text.startswith('\u25b6 '):
                text = text[2:]

            if i == self._current_file_index:
                item.setText(f'\u25b6 {text}')
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            else:
                item.setText(text)
                font = item.font()
                font.setBold(False)
                item.setFont(font)

        self._update_button_states()

    def _on_add(self):
        """Add files to the playlist via file dialog."""
        files, _ = QFileDialog.getOpenFileNames(
            self, 'Add Files to Playlist', '', AUDIO_FILE_FILTER)

        if files:
            self._player.add_files(files)

    def _on_remove(self):
        """Remove the selected file from the playlist."""
        selected = self._list.currentRow()
        if selected < 0 or selected == self._current_file_index:
            return

        if self._player.remove_file(selected):
            pass  # update_playlist() is called by Player.remove_file via window

    def _on_load(self):
        """Load a playlist from an M3U file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Load Playlist', '', M3U_FILE_FILTER)

        if file_path:
            paths = _parse_m3u(file_path)
            if paths:
                self._player.load_playlist(paths)

    def _on_save(self):
        """Save the current playlist to an M3U file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, 'Save Playlist', '', M3U_FILE_FILTER)

        if file_path:
            if not file_path.lower().endswith('.m3u'):
                file_path += '.m3u'
            _write_m3u(file_path, self._player.get_audio_files())

    def _update_button_states(self):
        """Enable/disable buttons based on current state."""
        selected = self._list.currentRow()
        has_selection = selected >= 0
        is_current = selected == self._current_file_index

        self._btn_remove.setEnabled(has_selection and not is_current)

    def closeEvent(self, event):
        """Hide instead of destroying when closed."""
        self.hide()
        event.ignore()
