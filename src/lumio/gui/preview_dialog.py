"""In-app media preview dialogs: Image (zoom/pan), Video, Audio."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap, QPolygon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t


def _fmt_ms(ms: int) -> str:
    """Format milliseconds as MM:SS."""
    s = max(0, ms // 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


# ---------------------------------------------------------------------------
# Shared player controls (video + audio)
# ---------------------------------------------------------------------------

class _PlayerControls(QWidget):
    """Play/pause + progress + time + volume.  Attach to a QMediaPlayer."""

    def __init__(self, player: QMediaPlayer, audio: QAudioOutput, parent=None):
        super().__init__(parent)
        self._player = player
        self._dragging = False

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 8)
        row.setSpacing(8)

        # Play / pause
        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(32, 28)
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.clicked.connect(self._toggle_play)
        row.addWidget(self._play_btn)

        # Progress slider
        self._progress = QSlider(Qt.Orientation.Horizontal)
        self._progress.setMinimumWidth(200)
        self._progress.sliderPressed.connect(self._on_press)
        self._progress.sliderMoved.connect(self._on_move)
        self._progress.sliderReleased.connect(self._on_release)
        row.addWidget(self._progress, 1)

        # Time label
        self._time = QLabel("00:00 / 00:00")
        self._time.setFixedWidth(100)
        self._time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self._time)

        # Volume
        vol = QLabel("🔊")
        row.addWidget(vol)
        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setFixedWidth(80)
        self._vol.setRange(0, 100)
        self._vol.setValue(80)
        self._vol.valueChanged.connect(lambda v: audio.setVolume(v / 100))
        row.addWidget(self._vol)

        # Signals
        player.positionChanged.connect(self._on_pos)
        player.durationChanged.connect(self._on_dur)
        player.playbackStateChanged.connect(self._on_state)
        audio.setVolume(0.8)

    # ---- slots ----

    def _toggle_play(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_pos(self, pos: int):
        if not self._dragging:
            self._progress.setValue(pos)
        self._time.setText(f"{_fmt_ms(pos)} / {_fmt_ms(self._player.duration())}")

    def _on_dur(self, dur: int):
        self._progress.setRange(0, dur)
        self._time.setText(f"00:00 / {_fmt_ms(dur)}")

    def _on_state(self, state):
        self._play_btn.setText("⏸" if state == QMediaPlayer.PlaybackState.PlayingState else "▶")

    def _on_press(self):
        self._dragging = True
        self._player.pause()

    def _on_move(self, pos: int):
        self._time.setText(f"{_fmt_ms(pos)} / {_fmt_ms(self._player.duration())}")

    def _on_release(self):
        self._dragging = False
        self._player.setPosition(self._progress.value())
        self._player.play()


# ---------------------------------------------------------------------------
# Image preview
# ---------------------------------------------------------------------------

class _ArrowButton(QWidget):
    """Painted triangle arrow — left or right. Emits clicked()."""
    clicked = Signal()

    def __init__(self, direction: str, parent=None):
        super().__init__(parent)
        self._dir = direction
        self._hovered = False
        self.setFixedWidth(44)
        self.setMinimumHeight(60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def sizeHint(self):
        return QSize(44, 120)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        alpha_bg = 60 if self._hovered else 20
        alpha_fg = 200 if self._hovered else 90
        # Semi-transparent background strip
        p.fillRect(QRect(0, 0, w, h), QColor(0, 0, 0, alpha_bg))
        # Triangle
        cx = w // 2
        cy = h // 2
        sz = 12
        if self._dir == "left":
            pts = QPolygon([QPoint(cx + sz // 2, cy - sz), QPoint(cx - sz // 2, cy), QPoint(cx + sz // 2, cy + sz)])
        else:
            pts = QPolygon([QPoint(cx - sz // 2, cy - sz), QPoint(cx + sz // 2, cy), QPoint(cx - sz // 2, cy + sz)])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, alpha_fg))
        p.drawPolygon(pts)
        p.end()

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class ImagePreviewDialog(QDialog):
    """Zoom/pan image viewer with multi-image navigation."""

    def __init__(self, file_paths: list[str] | str, parent=None):
        super().__init__(parent)
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        self._files = file_paths
        self._idx = 0
        self._zoom = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._dragging = False
        self._drag_start = (0, 0)
        self._base_scale = 1.0
        self._valid = False

        self._status = QLabel()
        self._status.setObjectName("muted")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addStretch(1)
        lay.addWidget(self._status)

        # Prev / Next arrow overlays (absolute positioned)
        self._prev_btn = _ArrowButton("left", self)
        self._prev_btn.clicked.connect(lambda: self._load_image(self._idx - 1))
        self._next_btn = _ArrowButton("right", self)
        self._next_btn.clicked.connect(lambda: self._load_image(self._idx + 1))

        self.setMouseTracking(True)
        self._load_image(0)

    def _build_error(self, msg: str):
        lay = QVBoxLayout(self)
        lbl = QLabel(msg)
        lbl.setObjectName("muted")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)

    def _load_image(self, idx: int):
        """Load image at index, reset zoom/pan."""
        if idx < 0 or idx >= len(self._files):
            return
        self._idx = idx
        self._pix = QPixmap(self._files[idx])
        if self._pix.isNull():
            self._valid = False
            self.setWindowTitle(Path(self._files[idx]).name)
            self._status.setText(t("preview_file_missing"))
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
            return
        self._valid = True
        self._zoom = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self.setWindowTitle(Path(self._files[idx]).name)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.resize(800, 600)
        self._recalc_base()
        self._update_status()
        self._prev_btn.setVisible(len(self._files) > 1 and self._idx > 0)
        self._next_btn.setVisible(len(self._files) > 1 and self._idx < len(self._files) - 1)
        self._prev_btn.raise_()
        self._next_btn.raise_()
        self.update()

    # ---- geometry ----

    def _content_rect(self):
        """Usable area (excluding status bar)."""
        h = self.height() - (self._status.height() if hasattr(self, '_status') and self._status else 24)
        return self.width(), h

    def _recalc_base(self):
        w, h = self._content_rect()
        pw, ph = self._pix.width(), self._pix.height()
        if pw == 0 or ph == 0:
            self._base_scale = 1.0
            return
        self._base_scale = min(w / pw, h / ph)
        sw, sh = int(pw * self._base_scale), int(ph * self._base_scale)
        self._offset_x = (w - sw) / 2
        self._offset_y = (h - sh) / 2

    def _update_status(self):
        pct = int(self._zoom * 100)
        w, h = self._pix.width(), self._pix.height()
        counter = f"  [{self._idx + 1}/{len(self._files)}]" if len(self._files) > 1 else ""
        self._status.setText(f"  {t('preview_zoom', pct=pct)}  ·  {w}×{h}{counter}  ")

    # ---- events ----

    def wheelEvent(self, event):
        if not self._valid:
            return
        pos = event.position()
        old_scale = self._base_scale * self._zoom
        old_cx = pos.x() - self._offset_x
        old_cy = pos.y() - self._offset_y

        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        self._zoom = max(0.1, min(5.0, self._zoom * factor))

        new_scale = self._base_scale * self._zoom
        self._offset_x = pos.x() - old_cx * new_scale / old_scale
        self._offset_y = pos.y() - old_cy * new_scale / old_scale
        self._update_status()
        self.update()

    def mousePressEvent(self, event):
        if not self._valid:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start = (event.position().x(), event.position().y())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if not self._valid:
            return
        if self._dragging:
            dx = event.position().x() - self._drag_start[0]
            dy = event.position().y() - self._drag_start[1]
            self._offset_x += dx
            self._offset_y += dy
            self._drag_start = (event.position().x(), event.position().y())
            self.update()

    def mouseReleaseEvent(self, event):
        if not self._valid:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event):
        if not self._valid:
            return
        self._zoom = 1.0
        self._recalc_base()
        self._update_status()
        self.update()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
        elif key == Qt.Key.Key_Left and self._idx > 0:
            self._load_image(self._idx - 1)
        elif key == Qt.Key.Key_Right and self._idx < len(self._files) - 1:
            self._load_image(self._idx + 1)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._valid or self._pix.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        s = self._base_scale * self._zoom
        w = max(1, int(self._pix.width() * s))
        h = max(1, int(self._pix.height() * s))
        p.drawPixmap(int(self._offset_x), int(self._offset_y), w, h, self._pix)
        p.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_arrows()
        if self._valid and not self._pix.isNull():
            self._recalc_base()
            self.update()

    def _layout_arrows(self):
        """Position arrow buttons at left/right edges, vertically centered."""
        bh = min(200, self.height() - 60)
        by = (self.height() - bh) // 2
        self._prev_btn.setGeometry(0, by, 44, bh)
        self._next_btn.setGeometry(self.width() - 44, by, 44, bh)


# ---------------------------------------------------------------------------
# Video preview
# ---------------------------------------------------------------------------

class VideoPreviewDialog(QDialog):
    """Video player with built-in controls."""

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(Path(file_path).name)
        self.resize(900, 640)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Video widget (dark background)
        self._video = QVideoWidget()
        self._video.setMinimumHeight(300)
        self._video.setStyleSheet("background-color: #000;")
        lay.addWidget(self._video, 1)

        # Error label (hidden by default)
        self._error = QLabel()
        self._error.setObjectName("muted")
        self._error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error.setVisible(False)
        lay.addWidget(self._error)

        # Player
        self._audio = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video)
        self._player.errorOccurred.connect(self._on_error)
        if file_path.startswith(("http://", "https://")):
            self.setWindowTitle(file_path.split("/")[-1][:40])
            self._player.setSource(QUrl(file_path))
        else:
            self._player.setSource(QUrl.fromLocalFile(file_path))
        self._player.play()

        # Controls
        self._controls = _PlayerControls(self._player, self._audio)
        lay.addWidget(self._controls)

    def _on_error(self, err, msg):
        self._player.stop()
        self._controls.setVisible(False)
        self._error.setText(f"{t('preview_format_error')}\n({msg})")
        self._error.setVisible(True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_Space:
            if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self._player.pause()
            else:
                self._player.play()

    def closeEvent(self, event):
        self._player.stop()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Audio preview
# ---------------------------------------------------------------------------

class AudioPreviewDialog(QDialog):
    """Audio player (no video area)."""

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(Path(file_path).name)
        self.resize(440, 200)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(8)

        icon = QLabel("♪")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 48px; color: #7c8fff;")
        lay.addWidget(icon)

        name = QLabel(Path(file_path).stem)
        name.setObjectName("muted")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(name)

        # Error label (hidden)
        self._error = QLabel()
        self._error.setObjectName("muted")
        self._error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error.setVisible(False)
        lay.addWidget(self._error)

        # Player
        self._audio = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio)
        self._player.errorOccurred.connect(self._on_error)
        if file_path.startswith(("http://", "https://")):
            self.setWindowTitle(file_path.split("/")[-1][:40])
            self._player.setSource(QUrl(file_path))
        else:
            self._player.setSource(QUrl.fromLocalFile(file_path))
        self._player.play()

        # Controls
        self._controls = _PlayerControls(self._player, self._audio)
        lay.addWidget(self._controls)

    def _on_error(self, err, msg):
        self._player.stop()
        self._controls.setVisible(False)
        self._error.setText(f"{t('preview_format_error')}\n({msg})")
        self._error.setVisible(True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_Space:
            if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self._player.pause()
            else:
                self._player.play()

    def closeEvent(self, event):
        self._player.stop()
        super().closeEvent(event)
