import sys
import re
import json
import hmac
import hashlib
import secrets
import subprocess
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QFileDialog, QTextEdit, QTabWidget,
    QMessageBox, QDoubleSpinBox, QGroupBox, QFormLayout, QListWidget,
    QListWidgetItem, QSplitter, QInputDialog, QComboBox
)
from PyQt6.QtCore import QProcess, Qt, QSettings, pyqtSignal
from PyQt6.QtGui import QFont

DATABASE_FILENAME      = "watermark_database.json"
KEYS_SUBDIR            = "keys"
HMAC_SUBDIR            = "hmac"
KEY_EXT                = ".key"
HMAC_EXT               = ".hmac"
SETTINGS_ORG           = "Audiowmark-desktop"
SETTINGS_APP           = "Audiowmark-desktop"
SETTINGS_KEY_DIR       = "keys_directory"
PLACEHOLDER_NO_KEYS    = "(no keys — add one in Key Management)"
PLACEHOLDER_NO_SECRETS = "(no secrets — add one in Key Management)"

HELP_HTML = """
<html><body style="font-family: sans-serif; font-size: 13px; margin: 16px;">

<h2 style="color:#2b78e4;">Audiowmark-desktop — User Guide</h2>

<h3>Overview</h3>
<p>
This tool embeds invisible, cryptographically secured watermarks into audio files using
<b>audiowmark</b> (Stefan Westerfeld). The watermark survives MP3/OGG re-encoding at
128 kbit/s or higher and can be detected from a copy without the original file.
</p>
<p>
Each watermark payload is a <b>HMAC-SHA256</b> of your metadata — not the metadata itself.
This means the payload stored in the audio is a one-way cryptographic hash that cannot
be reversed to recover your text, and cannot be forged without your HMAC secret.
</p>

<hr/>

<h3>Requirements</h3>
<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;">
  <tr><th>Dependency</th><th>Purpose</th><th>Notes</th></tr>
  <tr><td><b>audiowmark</b></td><td>Core watermarking engine</td><td>Must be in PATH</td></tr>
  <tr><td><b>ffmpeg</b></td><td>MP3 input pre-processing</td><td>Required for MP3 files only</td></tr>
  <tr><td>Python 3 + PyQt6</td><td>GUI runtime</td><td>pip install pyqt6</td></tr>
</table>
<p style="color:#c0392b;"><b>Note:</b> For MP3 input, audiowmark internally uses libmpg123 which cannot
always determine the exact decoded frame count upfront. This causes silent output truncation.
The fix is to route MP3 through ffmpeg via pipe — this tool does that automatically.
Without ffmpeg, MP3 input is disabled.</p>

<hr/>

<h3>Tab: Add Watermark</h3>

<h4>File Selection</h4>
<ul>
  <li><b>Input File</b> — WAV, MP3, or FLAC. MP3 requires ffmpeg (see above).</li>
  <li><b>Output File</b> — WAV or FLAC. Set automatically to
      <code>inputname_watermarked.ext</code> when you select the input.
      MP3 input defaults to WAV output since MP3 write support depends on
      libsndfile version.</li>
</ul>

<h4>Watermark Metadata</h4>
<p>These fields describe what the watermark identifies. They are never stored
in the audio file directly — only their HMAC hash is embedded.</p>
<ul>
  <li><b>Copyright *</b> — Mandatory. E.g. <i>2026 Alice Music</i></li>
  <li><b>Artist</b> — Optional.</li>
  <li><b>Title</b> — Optional.</li>
  <li><b>Purpose</b> — Optional. E.g. <i>Promo Copy</i>, <i>Review</i>, <i>Mastering Reference</i></li>
  <li><b>Other</b> — Optional free-form field.</li>
</ul>
<p>Internally the fields are concatenated as:
<code>Copyright:...|Artist:...|Title:...|Purpose:...|Other:...</code>
and passed to HMAC-SHA256.</p>

<h4>Options</h4>
<ul>
  <li><b>Audiowmark Key</b> — Select the key to use for embedding.
      The key controls which frequency bands are modified.
      Without it, the watermark cannot be decoded.
      Managed in the Key Management tab.</li>
  <li><b>HMAC Secret</b> — Select the secret used to compute the payload hash.
      Without it, the database entry cannot be verified during decoding.
      Managed in the Key Management tab.</li>
  <li><b>Strength</b> — Range 5.0–20.0, default 10.0 (steps of 0.5).
      Higher values make the watermark more robust against lossy re-encoding
      and format conversions, but slightly more audible.
      The default of 10 survives MP3/OGG at 128 kbit/s or higher.
      Use 15+ for resilience against multiple conversions or low bitrates (64 kbit/s).</li>
</ul>

<h4>What Happens on Embed</h4>
<ol>
  <li>Metadata fields are joined into a pipe-separated string.</li>
  <li>HMAC-SHA256 is computed using the selected HMAC secret. The first 128 bits
      of the digest become the payload.</li>
  <li>The mapping <code>payload → metadata + key name + secret name</code> is
      saved to <code>watermark_database.json</code> in the Keys Directory.</li>
  <li><code>audiowmark add --key ... --strength ... input output payload</code>
      is executed. For MP3 input, ffmpeg is used as upstream pipe.</li>
</ol>

<hr/>

<h3>Tab: Get Watermark</h3>
<ul>
  <li>Select the watermarked audio file (WAV, FLAC, or MP3).</li>
  <li>All keys in the Keys Directory are tried automatically.
      You do not need to know which key was used.</li>
  <li>For each <code>pattern all</code> result returned by audiowmark,
      the decoded hash is looked up in <code>watermark_database.json</code>.</li>
  <li>A match displays the full metadata in <b>Decoded Watermark</b> and
      the verification details (key name, secret name, payload) in
      <b>Verified from Database</b>.</li>
  <li>A non-match means either a decoding error (false positive) or the file
      was watermarked with a key/secret not present in your Keys Directory.</li>
</ul>

<hr/>

<h3>Tab: Key Management</h3>

<h4>Keys Directory</h4>
<p>The root directory for all key material. Subdirectories
<code>keys/</code> and <code>hmac/</code> are created automatically.
The database file <code>watermark_database.json</code> is stored here too.
The selected path persists across restarts.</p>

<h4>Audiowmark Keys (.key)</h4>
<p>A 128-bit AES key generated by <code>audiowmark gen-key</code>.
It controls the pseudo-random embedding positions in the audio spectrum.
<b>Keep this secret.</b> Anyone with the key can decode and losslessly
remove your watermarks.</p>
<ul>
  <li><b>Generate New Key</b> — Enter a display name; the file is named after it.
      The name is stored inside the key file via <code>--name</code>.</li>
  <li><b>Delete</b> — Irreversible. All files watermarked with this key
      become permanently undecodable without a backup.</li>
</ul>

<h4>HMAC Secrets (.hmac)</h4>
<p>A 256-bit random secret used to compute the payload hash.
Independent from the audiowmark key — compromising one does not compromise the other.</p>
<ul>
  <li><b>Generate New Secret</b> — Creates a file containing 32 random hex bytes
      (256 bits). File permissions are set to 600.</li>
  <li><b>Delete</b> — Irreversible. Existing database entries become unmatchable:
      the watermark signal in the audio remains, but the hash cannot be verified
      against metadata without the secret.</li>
</ul>

<hr/>

<h3>Security Model</h3>
<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;">
  <tr><th>Property</th><th>This Tool</th></tr>
  <tr><td>Payload readable without key</td><td style="color:green;">No — private audiowmark key required</td></tr>
  <tr><td>Payload forgeable</td><td style="color:green;">No — HMAC secret required</td></tr>
  <tr><td>Watermark removable losslessly</td><td style="color:green;">No — private audiowmark key required</td></tr>
  <tr><td>False positives accepted</td><td style="color:green;">No — database lookup required</td></tr>
  <tr><td>Metadata recoverable from payload alone</td><td style="color:green;">No — one-way HMAC</td></tr>
  <tr><td>Multiple key rotation</td><td style="color:green;">Yes — all keys tried on decode</td></tr>
</table>

<hr/>

<h3>Watermark Strength Reference</h3>
<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;">
  <tr><th>Strength</th><th>Use Case</th></tr>
  <tr><td>5.0 – 7.0</td><td>Minimal audible impact; less robust. Not recommended below 5.</td></tr>
  <tr><td><b>10.0 (default)</b></td><td>Survives MP3/OGG at 128 kbit/s+. Good balance.</td></tr>
  <tr><td>13.0 – 15.0</td><td>Multiple conversions, low bitrate (64 kbit/s).</td></tr>
  <tr><td>15.0 – 20.0</td><td>Maximum robustness; slight audibility possible.</td></tr>
</table>

<hr/>

<h3>Database File</h3>
<p><code>watermark_database.json</code> in the Keys Directory maps each
HMAC payload to its metadata. Without this file, verified decoding is not
possible even if you have all keys and secrets. <b>Back it up alongside your keys.</b></p>

<hr/>

<h3>Typical Workflow</h3>
<ol>
  <li>Go to <b>Key Management</b>, select a Keys Directory, generate at least
      one audiowmark key and one HMAC secret.</li>
  <li>Go to <b>Add Watermark</b>, select your audio file, fill in Copyright
      (mandatory) and any other fields, select key and secret, click
      <i>Start Watermarking Process</i>.</li>
  <li>Distribute the watermarked output file.</li>
  <li>If you find a suspicious copy, go to <b>Get Watermark</b>, select the file,
      click <i>Find &amp; Decode Watermark</i>. A database match shows who it
      was issued to.</li>
</ol>

</body></html>
"""


class KeyManagerWidget(QWidget):
    """Manages audiowmark key files and HMAC secret files under a shared base directory."""

    keys_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_dir = None
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self._init_ui()
        # Restore previously selected directory on startup
        self._restore_directory()

    def _init_ui(self):
        layout = QVBoxLayout()

        dir_group = QGroupBox("Keys Directory")
        dir_layout = QHBoxLayout()
        self.dir_input = QLineEdit()
        self.dir_input.setReadOnly(True)
        self.dir_input.setPlaceholderText("Select directory for keys and HMAC secrets...")
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._select_base_dir)
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(btn_browse)
        dir_group.setLayout(dir_layout)
        layout.addWidget(dir_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Audiowmark keys panel
        keys_widget = QWidget()
        keys_layout = QVBoxLayout()
        keys_layout.addWidget(QLabel("Audiowmark Keys (.key)"))
        self.keys_list = QListWidget()
        keys_layout.addWidget(self.keys_list)
        btn_gen_key = QPushButton("Generate New Key...")
        btn_gen_key.clicked.connect(self._generate_key)
        btn_del_key = QPushButton("Delete Selected Key")
        btn_del_key.clicked.connect(self._delete_key)
        keys_layout.addWidget(btn_gen_key)
        keys_layout.addWidget(btn_del_key)
        keys_widget.setLayout(keys_layout)

        # HMAC secrets panel
        hmac_widget = QWidget()
        hmac_layout = QVBoxLayout()
        hmac_layout.addWidget(QLabel("HMAC Secrets (.hmac)"))
        self.hmac_list = QListWidget()
        hmac_layout.addWidget(self.hmac_list)
        btn_gen_hmac = QPushButton("Generate New HMAC Secret...")
        btn_gen_hmac.clicked.connect(self._generate_hmac_secret)
        btn_del_hmac = QPushButton("Delete Selected Secret")
        btn_del_hmac.clicked.connect(self._delete_hmac_secret)
        hmac_layout.addWidget(btn_gen_hmac)
        hmac_layout.addWidget(btn_del_hmac)
        hmac_widget.setLayout(hmac_layout)

        splitter.addWidget(keys_widget)
        splitter.addWidget(hmac_widget)
        layout.addWidget(splitter)
        self.setLayout(layout)

    def _restore_directory(self):
        saved = self.settings.value(SETTINGS_KEY_DIR, "")
        if saved and Path(saved).is_dir():
            self._apply_base_dir(Path(saved))

    def _select_base_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Keys Directory")
        if not path:
            return
        self._apply_base_dir(Path(path))
        self.settings.setValue(SETTINGS_KEY_DIR, str(self.base_dir))

    def _apply_base_dir(self, path):
        self.base_dir = path
        self.dir_input.setText(str(self.base_dir))
        (self.base_dir / KEYS_SUBDIR).mkdir(exist_ok=True)
        (self.base_dir / HMAC_SUBDIR).mkdir(exist_ok=True)
        self.refresh_lists()

    def refresh_lists(self):
        if not self.base_dir:
            return

        self.keys_list.clear()
        for f in sorted((self.base_dir / KEYS_SUBDIR).glob(f"*{KEY_EXT}")):
            item = QListWidgetItem(f.name)
            item.setData(Qt.ItemDataRole.UserRole, str(f))
            self.keys_list.addItem(item)

        self.hmac_list.clear()
        for f in sorted((self.base_dir / HMAC_SUBDIR).glob(f"*{HMAC_EXT}")):
            item = QListWidgetItem(f.name)
            item.setData(Qt.ItemDataRole.UserRole, str(f))
            self.hmac_list.addItem(item)

        self.keys_changed.emit()

    def _generate_key(self):
        if not self.base_dir:
            QMessageBox.warning(self, "Warning", "Please select a Keys Directory first.")
            return

        name, ok = QInputDialog.getText(self, "Generate Key", "Key display name (used as --name):")
        if not ok or not name.strip():
            return

        safe     = re.sub(r"[^\w\-]", "_", name.strip())
        key_path = self.base_dir / KEYS_SUBDIR / f"{safe}{KEY_EXT}"

        if key_path.exists():
            QMessageBox.warning(self, "Warning", f"Key '{key_path.name}' already exists.")
            return

        result = subprocess.run(
            ["audiowmark", "gen-key", str(key_path), "--name", name.strip()],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            QMessageBox.critical(self, "Error", f"audiowmark gen-key failed:\n{result.stderr}")
            return

        self.refresh_lists()

    def _delete_key(self):
        item = self.keys_list.currentItem()
        if not item:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        reply = QMessageBox.question(
            self, "Confirm Delete — Audiowmark Key",
            f"Delete key '{path.name}'?\n\n"
            f"WARNING: This key controls the watermark embedding positions in the audio spectrum.\n"
            f"Without it, 'audiowmark get' will return NO results for any file watermarked with this key.\n"
            f"All previously watermarked files will become permanently unverifiable.\n\n"
            f"Make sure you have a backup before proceeding.\n\n"
            f"This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            path.unlink(missing_ok=True)
            self.refresh_lists()

    def _generate_hmac_secret(self):
        if not self.base_dir:
            QMessageBox.warning(self, "Warning", "Please select a Keys Directory first.")
            return

        name, ok = QInputDialog.getText(self, "Generate HMAC Secret", "Secret name:")
        if not ok or not name.strip():
            return

        safe      = re.sub(r"[^\w\-]", "_", name.strip())
        hmac_path = self.base_dir / HMAC_SUBDIR / f"{safe}{HMAC_EXT}"

        if hmac_path.exists():
            QMessageBox.warning(self, "Warning", f"Secret '{hmac_path.name}' already exists.")
            return

        # 32 random bytes as hex — 256-bit secret
        hmac_path.write_text(secrets.token_hex(32))
        hmac_path.chmod(0o600)
        self.refresh_lists()

    def _delete_hmac_secret(self):
        item = self.hmac_list.currentItem()
        if not item:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        reply = QMessageBox.question(
            self, "Confirm Delete — HMAC Secret",
            f"Delete HMAC secret '{path.name}'?\n\n"
            f"WARNING: This secret was used to compute the HMAC payload stored in the watermark database.\n"
            f"Without it, previously created database entries CANNOT be re-verified —\n"
            f"the watermark signal in the audio files remains intact, but the decoded hash\n"
            f"will no longer match any entry and the metadata (Copyright, Artist etc.) will be lost.\n\n"
            f"Make sure you have a backup before proceeding.\n\n"
            f"This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            path.unlink(missing_ok=True)
            self.refresh_lists()

    # --- Public accessors ---

    def get_all_key_paths(self):
        return [
            self.keys_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.keys_list.count())
        ]

    def get_all_hmac_paths(self):
        return [
            self.hmac_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.hmac_list.count())
        ]


class AudiowmarkGUI(QWidget):
    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Audiowmark-desktop")
        self.resize(820, 740)

        main_layout = QVBoxLayout()

        # ffmpeg check must happen before tabs are created so note labels can be set
        self.ffmpeg_proc      = None
        self.ffmpeg_available = self._check_ffmpeg()

        # KeyManagerWidget restores its directory on init and emits keys_changed,
        # but the signal is connected only after the combo boxes are created below.
        self.key_manager = KeyManagerWidget()

        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_add_tab(),  "Add Watermark")
        self.tabs.addTab(self._create_get_tab(),  "Get Watermark")
        self.tabs.addTab(self.key_manager,        "Key Management")
        self.tabs.addTab(self._create_help_tab(), "Help")
        main_layout.addWidget(self.tabs)

        log_group = QGroupBox("Console Output")
        log_layout = QVBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Courier New", 10))
        self.log_output.setMaximumHeight(160)
        log_layout.addWidget(self.log_output)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        self.setLayout(main_layout)

        # Connect signal after combo boxes exist, then populate once with current state
        self.key_manager.keys_changed.connect(self._refresh_key_combos)
        self._refresh_key_combos()

        self.process = QProcess()
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._process_finished)

    def _create_add_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        # File selection
        file_group = QGroupBox("File Selection")
        file_layout = QFormLayout()

        self.add_in_input = QLineEdit()
        self.add_in_input.textChanged.connect(self._auto_set_output)
        btn_in = QPushButton("Browse...")
        btn_in.clicked.connect(
            lambda: self._browse_open(self.add_in_input, "Select Input Audio File")
        )
        row_in = QHBoxLayout()
        row_in.addWidget(self.add_in_input)
        row_in.addWidget(btn_in)

        self.add_out_input = QLineEdit()
        btn_out = QPushButton("Browse...")
        btn_out.clicked.connect(
            lambda: self._browse_save(self.add_out_input, "Save Watermarked File")
        )
        row_out = QHBoxLayout()
        row_out.addWidget(self.add_out_input)
        row_out.addWidget(btn_out)

        self.ffmpeg_note_add = QLabel()
        self.ffmpeg_note_add.setWordWrap(True)

        file_layout.addRow("Input File (WAV / MP3 / FLAC):", row_in)
        file_layout.addRow("Output File (WAV / FLAC):", row_out)
        file_layout.addRow(self.ffmpeg_note_add)
        file_group.setLayout(file_layout)

        # Metadata
        meta_group = QGroupBox("Watermark Metadata")
        meta_layout = QFormLayout()
        self.copyright_input = QLineEdit()
        self.copyright_input.setPlaceholderText("Required")
        self.artist_input = QLineEdit()
        self.artist_input.setPlaceholderText("Optional")
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Optional")
        self.purpose_input = QLineEdit()
        self.purpose_input.setPlaceholderText("Optional — e.g. Review Copy, Promo")
        self.other_input = QLineEdit()
        self.other_input.setPlaceholderText("Optional")
        meta_layout.addRow("Copyright *:", self.copyright_input)
        meta_layout.addRow("Artist:",      self.artist_input)
        meta_layout.addRow("Title:",       self.title_input)
        meta_layout.addRow("Purpose:",     self.purpose_input)
        meta_layout.addRow("Other:",       self.other_input)
        meta_group.setLayout(meta_layout)

        # Options — key/hmac dropdowns populated from Key Management
        opts_group = QGroupBox("Options")
        opts_layout = QFormLayout()

        self.key_combo  = QComboBox()
        self.hmac_combo = QComboBox()

        self.strength_input = QDoubleSpinBox()
        self.strength_input.setRange(5.0, 20.0)
        self.strength_input.setValue(10.0)
        self.strength_input.setSingleStep(0.5)
        self.strength_input.setDecimals(1)

        opts_layout.addRow("Audiowmark Key:", self.key_combo)
        opts_layout.addRow("HMAC Secret:",    self.hmac_combo)
        opts_layout.addRow("Strength:",       self.strength_input)
        opts_group.setLayout(opts_layout)

        self.btn_run_add = QPushButton("Start Watermarking Process")
        self.btn_run_add.setStyleSheet(
            "background-color: #2b78e4; color: white; font-weight: bold; padding: 8px;"
        )
        self.btn_run_add.clicked.connect(self._run_add_watermark)

        layout.addWidget(file_group)
        layout.addWidget(meta_group)
        layout.addWidget(opts_group)
        layout.addWidget(self.btn_run_add)
        widget.setLayout(layout)
        return widget

    def _create_get_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        file_group = QGroupBox("File to Scan")
        file_layout = QFormLayout()
        self.get_in_input = QLineEdit()
        btn_get = QPushButton("Browse...")
        btn_get.clicked.connect(
            lambda: self._browse_open(self.get_in_input, "Select Watermarked File")
        )
        row_get = QHBoxLayout()
        row_get.addWidget(self.get_in_input)
        row_get.addWidget(btn_get)
        self.ffmpeg_note_get = QLabel()
        self.ffmpeg_note_get.setWordWrap(True)

        file_layout.addRow("Watermarked Audio (WAV / MP3 / FLAC):", row_get)
        file_layout.addRow(self.ffmpeg_note_get)
        file_group.setLayout(file_layout)

        hint = QLabel("All keys from Key Management will be tried automatically.")
        hint.setStyleSheet("color: #666; font-style: italic;")

        self.btn_run_get = QPushButton("Find & Decode Watermark")
        self.btn_run_get.setStyleSheet(
            "background-color: #2ba7e4; color: white; font-weight: bold; padding: 8px;"
        )
        self.btn_run_get.clicked.connect(self._run_get_watermark)

        # Decoded metadata fields
        decoded_group = QGroupBox("Decoded Watermark")
        decoded_layout = QFormLayout()
        self.res_copyright = QLabel("-")
        self.res_artist    = QLabel("-")
        self.res_title     = QLabel("-")
        self.res_purpose   = QLabel("-")
        self.res_other     = QLabel("-")
        decoded_layout.addRow("Copyright:", self.res_copyright)
        decoded_layout.addRow("Artist:",    self.res_artist)
        decoded_layout.addRow("Title:",     self.res_title)
        decoded_layout.addRow("Purpose:",   self.res_purpose)
        decoded_layout.addRow("Other:",     self.res_other)
        decoded_group.setLayout(decoded_layout)

        # Database verification details
        verified_group = QGroupBox("Verified from Database")
        verified_layout = QFormLayout()
        self.res_ver_key     = QLabel("-")
        self.res_ver_hmac    = QLabel("-")
        self.res_ver_payload = QLabel("-")
        self.res_ver_payload.setFont(QFont("Courier New", 9))
        self.res_ver_payload.setWordWrap(True)
        verified_layout.addRow("Audiowmark Key:", self.res_ver_key)
        verified_layout.addRow("HMAC Secret:",    self.res_ver_hmac)
        verified_layout.addRow("Payload:",        self.res_ver_payload)
        verified_group.setLayout(verified_layout)

        layout.addWidget(file_group)
        layout.addWidget(hint)
        layout.addWidget(self.btn_run_get)
        layout.addWidget(decoded_group)
        layout.addWidget(verified_group)
        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_help_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        help_view = QTextEdit()
        help_view.setReadOnly(True)
        help_view.setHtml(HELP_HTML)
        layout.addWidget(help_view)
        widget.setLayout(layout)
        return widget

    def _refresh_key_combos(self):
        """Repopulate key and HMAC combo boxes from the current key manager state."""
        self.key_combo.clear()
        key_paths = self.key_manager.get_all_key_paths()
        if key_paths:
            for path in key_paths:
                self.key_combo.addItem(Path(path).name, userData=path)
        else:
            self.key_combo.addItem(PLACEHOLDER_NO_KEYS, userData=None)

        self.hmac_combo.clear()
        hmac_paths = self.key_manager.get_all_hmac_paths()
        if hmac_paths:
            for path in hmac_paths:
                self.hmac_combo.addItem(Path(path).name, userData=path)
        else:
            self.hmac_combo.addItem(PLACEHOLDER_NO_SECRETS, userData=None)

        # Update ffmpeg availability notes now that both labels exist
        self._update_ffmpeg_notes()

    # --- File dialogs ---

    def _browse_open(self, line_edit, title):
        path, _ = QFileDialog.getOpenFileName(
            self, title, "", "Audio Files (*.wav *.mp3 *.flac);;All Files (*)"
        )
        if path:
            line_edit.setText(path)

    def _browse_save(self, line_edit, title):
        path, _ = QFileDialog.getSaveFileName(
            self, title, "", "Audio Files (*.wav *.flac *.aiff);;WAV (*.wav);;FLAC (*.flac);;AIFF (*.aiff);;All Files (*)"
        )
        if path:
            line_edit.setText(path)

    def _auto_set_output(self, input_path):
        """Auto-populate output path based on input path.
        MP3 input defaults to WAV output since MP3 write support depends on libsndfile version.
        All other formats keep their extension."""
        if not input_path.strip():
            return
        p      = Path(input_path.strip())
        ext    = p.suffix.lower()
        # MP3 output requires libsndfile >= 1.1.0 which is not universally available
        out_ext = ".wav" if ext == ".mp3" else ext if ext in (".wav", ".flac", ".aiff") else ".wav"
        out_path = p.parent / f"{p.stem}_watermarked{out_ext}"
        self.add_out_input.setText(str(out_path))



    def _build_metadata_string(self):
        """Build pipe-separated metadata string. Copyright is always first."""
        parts = [f"Copyright:{self.copyright_input.text().strip()}"]
        for key, widget in [
            ("Artist",  self.artist_input),
            ("Title",   self.title_input),
            ("Purpose", self.purpose_input),
            ("Other",   self.other_input),
        ]:
            val = widget.text().strip()
            if val:
                parts.append(f"{key}:{val}")
        return "|".join(parts)

    def _compute_hmac_payload(self, metadata_string, hmac_secret_path):
        """Compute HMAC-SHA256(secret, metadata). Returns first 32 hex chars (128 bits)."""
        secret_bytes = bytes.fromhex(Path(hmac_secret_path).read_text().strip())
        msg_bytes    = metadata_string.encode("utf-8")
        digest       = hmac.new(secret_bytes, msg_bytes, hashlib.sha256).hexdigest()
        return digest[:32]

    # --- Database helpers ---

    def _db_path(self):
        return self.key_manager.base_dir / DATABASE_FILENAME if self.key_manager.base_dir else None

    def _load_database(self):
        path = self._db_path()
        if path and path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
        return {}

    def _save_database(self, db):
        path = self._db_path()
        if path:
            path.write_text(json.dumps(db, indent=2, ensure_ascii=False))

    # --- Watermark operations ---

    def _run_add_watermark(self):
        infile        = self.add_in_input.text().strip()
        outfile       = self.add_out_input.text().strip()
        copyright_val = self.copyright_input.text().strip()

        if not infile or not outfile:
            QMessageBox.critical(self, "Error", "Input and output files are required.")
            return
        if not copyright_val:
            QMessageBox.critical(self, "Error", "Copyright is a mandatory field.")
            return

        key_path  = self.key_combo.currentData()
        hmac_path = self.hmac_combo.currentData()

        if not key_path:
            QMessageBox.critical(self, "Error", "No audiowmark key selected.\nAdd keys in Key Management.")
            return
        if not hmac_path:
            QMessageBox.critical(self, "Error", "No HMAC secret selected.\nAdd secrets in Key Management.")
            return

        metadata_string = self._build_metadata_string()

        try:
            payload = self._compute_hmac_payload(metadata_string, hmac_path)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"HMAC computation failed:\n{exc}")
            return

        key_name  = Path(key_path).name
        hmac_name = Path(hmac_path).name

        # Persist hash -> metadata entry so get tab can look it up
        db = self._load_database()
        db[payload] = {
            "metadata":    metadata_string,
            "key":         key_name,
            "hmac_secret": hmac_name,
        }
        self._save_database(db)

        self.log_output.clear()
        self.log_output.append(f"Metadata              : {metadata_string}")
        self.log_output.append(f"Used Audiowmark Key   : {key_name}")
        self.log_output.append(f"Used HMAC Secret      : {hmac_name}")
        self.log_output.append(
            f"Generated HMAC Payload: {payload}  (HMAC-SHA256, first 128 bits)\n"
        )
        self._toggle_buttons(False)

        if Path(infile).suffix.lower() == ".mp3":
            if not self.ffmpeg_available:
                QMessageBox.critical(self, "Error",
                    "MP3 input requires ffmpeg, but it was not found in PATH.\n"
                    "Please install ffmpeg and restart the application.")
                self._toggle_buttons(True)
                return
            self.log_output.append("[MP3 input: routing through ffmpeg pipe]\n")
            self._start_with_ffmpeg_pipe(
                ["add", "--input-format", "wav-pipe",
                 "--key", key_path,
                 "--strength", str(self.strength_input.value()),
                 "-", outfile, payload],
                infile
            )
        else:
            self.process.start("audiowmark", [
                "add",
                "--key", key_path,
                "--strength", str(self.strength_input.value()),
                infile, outfile, payload,
            ])

    def _run_get_watermark(self):
        infile    = self.get_in_input.text().strip()
        key_paths = self.key_manager.get_all_key_paths()

        if not infile:
            QMessageBox.critical(self, "Error", "Please select a file to analyze.")
            return
        if not key_paths:
            QMessageBox.critical(self, "Error", "No keys available. Add keys in the Key Management tab.")
            return

        for label in (
            self.res_copyright, self.res_artist,    self.res_title,
            self.res_purpose,   self.res_other,
            self.res_ver_key,   self.res_ver_hmac,  self.res_ver_payload,
        ):
            label.setText("-")

        self.log_output.clear()
        self.log_output.append(f"Scanning with {len(key_paths)} key(s)...\n")
        self._toggle_buttons(False)

        if Path(infile).suffix.lower() == ".mp3":
            if not self.ffmpeg_available:
                QMessageBox.critical(self, "Error",
                    "MP3 input requires ffmpeg, but it was not found in PATH.\n"
                    "Please install ffmpeg and restart the application.")
                self._toggle_buttons(True)
                return
            self.log_output.append("[MP3 input: routing through ffmpeg pipe]\n")
            args = ["get", "--input-format", "wav-pipe"]
            for kp in key_paths:
                args += ["--key", kp]
            args.append("-")
            self._start_with_ffmpeg_pipe(args, infile)
        else:
            args = ["get"]
            for kp in key_paths:
                args += ["--key", kp]
            args.append(infile)
            self.process.start("audiowmark", args)

    # --- ffmpeg pipe helpers ---

    def _check_ffmpeg(self):
        """Return True if ffmpeg is available in PATH."""
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _update_ffmpeg_notes(self):
        """Set ffmpeg availability note labels on both tabs."""
        if self.ffmpeg_available:
            msg   = "MP3 input: ffmpeg found — full-length processing enabled."
            style = "color: #2a7a2a; font-style: italic; font-size: 11px;"
        else:
            msg   = "WARNING: ffmpeg not found in PATH. MP3 input will be disabled. Install ffmpeg to enable it."
            style = "color: #c0392b; font-weight: bold; font-size: 11px;"
        for label in (self.ffmpeg_note_add, self.ffmpeg_note_get):
            label.setText(msg)
            label.setStyleSheet(style)

    def _start_with_ffmpeg_pipe(self, audiowmark_args, mp3_path):
        """Route MP3 input through ffmpeg to avoid libmpg123 frame count truncation.
        audiowmark reads WAV from stdin via --input-format wav-pipe."""
        self.ffmpeg_proc = QProcess()
        self.ffmpeg_proc.setStandardOutputProcess(self.process)
        self.ffmpeg_proc.readyReadStandardError.connect(self._handle_ffmpeg_stderr)
        # Downstream (audiowmark) must be started before upstream (ffmpeg) writes to it
        self.process.start("audiowmark", audiowmark_args)
        self.ffmpeg_proc.start("ffmpeg", ["-i", mp3_path, "-f", "wav", "-"])

    def _handle_ffmpeg_stderr(self):
        """Forward only error-level ffmpeg stderr lines to the log."""
        data = self.ffmpeg_proc.readAllStandardError().data().decode("utf-8", errors="ignore")
        for line in data.split("\n"):
            if any(w in line.lower() for w in ("error", "invalid", "fail", "unable")):
                self.log_output.append(f"[ffmpeg] {line}")

    # --- Process output handlers ---

    def _handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode("utf-8", errors="ignore")
        self.log_output.append(data)

        db = self._load_database()
        for line in data.split("\n"):
            if "pattern" in line and "all" in line:
                match = re.search(r"pattern\s+all\s+([0-9a-fA-F]{32})", line)
                if not match:
                    continue
                found_hash = match.group(1)
                if found_hash in db:
                    entry        = db[found_hash]
                    metadata_str = entry["metadata"]
                    key_name     = entry.get("key",         "-")
                    hmac_name    = entry.get("hmac_secret", "-")

                    self.log_output.append("\n=== WATERMARK VERIFIED FROM DATABASE ===")
                    self.log_output.append(f"Metadata               : {metadata_str}")
                    self.log_output.append(f"Matched Audiowmark Key : {key_name}")
                    self.log_output.append(f"Matched HMAC Secret    : {hmac_name}")
                    self.log_output.append(
                        f"Matched Payload        : {found_hash}  (HMAC-SHA256, first 128 bits)"
                    )

                    self._populate_result_fields(metadata_str)
                    self.res_ver_key.setText(key_name)
                    self.res_ver_hmac.setText(hmac_name)
                    self.res_ver_payload.setText(found_hash)
                else:
                    self.log_output.append(
                        f"\n=== Hash decoded but not found in local database: {found_hash} ==="
                    )

    def _handle_stderr(self):
        data = self.process.readAllStandardError().data().decode("utf-8", errors="ignore")
        self.log_output.append(data)

    def _process_finished(self):
        self._toggle_buttons(True)
        self.log_output.append("\n=== Task Finished ===")

    # --- UI helpers ---

    def _toggle_buttons(self, enabled):
        self.btn_run_add.setEnabled(enabled)
        self.btn_run_get.setEnabled(enabled)

    def _populate_result_fields(self, metadata_string):
        fields = {}
        for part in metadata_string.split("|"):
            key, _, value = part.partition(":")
            fields[key] = value
        self.res_copyright.setText(fields.get("Copyright", "-"))
        self.res_artist.setText(fields.get("Artist",    "-"))
        self.res_title.setText(fields.get("Title",     "-"))
        self.res_purpose.setText(fields.get("Purpose",   "-"))
        self.res_other.setText(fields.get("Other",     "-"))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = AudiowmarkGUI()
    window.show()
    sys.exit(app.exec())
