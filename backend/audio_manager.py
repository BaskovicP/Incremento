from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

try:
    from .content_safety import external_plain_text, external_plain_text_to_anki_html
    from .note_metadata import (
        INCREMENTO_METADATA_FIELDS,
        apply_incremento_metadata,
        build_incremento_metadata,
    )
    from .note_type_updates import NoteTypeSpec, ensure_note_type
    from .operation_journal import ImportOperation
except ImportError:
    from content_safety import external_plain_text, external_plain_text_to_anki_html  # type: ignore
    from note_metadata import (  # type: ignore
        INCREMENTO_METADATA_FIELDS,
        apply_incremento_metadata,
        build_incremento_metadata,
    )
    from note_type_updates import NoteTypeSpec, ensure_note_type  # type: ignore
    from operation_journal import ImportOperation  # type: ignore


AUDIO_NOTE_TYPE = "Incremento Audio"
AUDIO_FIELD = "Audio"
AUDIO_FILENAME_FIELD = "Audio_Filename"
PROGRESS_KEY_FIELD = "Progress_Key"
AUDIO_NOTES_FIELD = "Notes"
SUPPORTED_AUDIO_EXTENSIONS = (".mp3", ".m4a", ".aac", ".wav")
MAX_AUDIO_BYTES = 100_000_000

_SAFE_STEM_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_MAX_STEM_CHARS = 60

CARD_TEMPLATE = r"""
<div class="incremento-audio-card" data-progress-key="{{text:Progress_Key}}">
  <div class="incremento-audio-title">{{text:Title}}</div>
  <audio id="incremento-audio-player" controls preload="metadata" src="{{text:Audio_Filename}}"></audio>
  {{#Notes}}<div class="incremento-audio-notes">{{Notes}}</div>{{/Notes}}
  <div class="incremento-audio-resume" id="incremento-audio-resume" aria-live="polite"></div>
</div>
<style>
  .incremento-audio-card { max-width: 760px; margin: 0 auto; padding: 24px 16px; font-family: sans-serif; }
  .incremento-audio-title { margin-bottom: 18px; font-size: 1.35em; font-weight: 650; }
  #incremento-audio-player { width: 100%; min-height: 48px; }
  .incremento-audio-notes { margin-top: 20px; line-height: 1.5; text-align: left; }
  .incremento-audio-resume { min-height: 1.2em; margin-top: 8px; color: #888; font-size: 0.82em; }
</style>
<script>
(() => {
  const root = document.querySelector('.incremento-audio-card');
  const player = document.getElementById('incremento-audio-player');
  const status = document.getElementById('incremento-audio-resume');
  if (!root || !player) return;

  const progressKey = String(root.dataset.progressKey || '').trim();
  if (!/^[a-f0-9]{32}$/.test(progressKey)) return;
  const storageKey = 'incremento.audio.position.v1:' + progressKey;
  let lastSavedSecond = -1;

  const formatTime = (seconds) => {
    const value = Math.max(0, Math.floor(Number(seconds) || 0));
    const hours = Math.floor(value / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    const secs = value % 60;
    return hours
      ? `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
      : `${minutes}:${String(secs).padStart(2, '0')}`;
  };

  const savePosition = () => {
    const position = Number(player.currentTime);
    if (!Number.isFinite(position) || position < 0) return;
    const wholeSecond = Math.floor(position);
    if (wholeSecond === lastSavedSecond) return;
    try {
      localStorage.setItem(storageKey, String(position));
      lastSavedSecond = wholeSecond;
    } catch (_error) {
      // Playback remains available when a client disables persistent web storage.
    }
  };

  player.addEventListener('loadedmetadata', () => {
    let saved = 0;
    try {
      saved = Number(localStorage.getItem(storageKey) || 0);
    } catch (_error) {
      saved = 0;
    }
    const duration = Number(player.duration);
    if (!Number.isFinite(saved) || saved <= 1) return;
    if (Number.isFinite(duration) && saved >= duration - 1) return;
    try {
      player.currentTime = saved;
      lastSavedSecond = Math.floor(saved);
      if (status) status.textContent = `Resume ${formatTime(saved)}`;
    } catch (_error) {
      // Some clients allow seeking only after more media has buffered.
    }
  });

  player.addEventListener('timeupdate', savePosition);
  player.addEventListener('pause', savePosition);
  player.addEventListener('ended', () => {
    try { localStorage.removeItem(storageKey); } catch (_error) {}
    lastSavedSecond = -1;
    if (status) status.textContent = '';
  });
  window.addEventListener('pagehide', savePosition, { once: true });
})();
</script>
""".strip()


def _validated_source(source_path: str) -> tuple[Path, str]:
    source = Path(str(source_path or "").strip()).expanduser()
    if not source.is_file():
        raise ValueError("Selected audio file does not exist.")
    extension = source.suffix.lower()
    if extension not in SUPPORTED_AUDIO_EXTENSIONS:
        raise ValueError("Audio must be an MP3, M4A, AAC, or WAV file.")
    size = os.path.getsize(source)
    if size <= 0:
        raise ValueError("Selected audio file is empty.")
    if size > MAX_AUDIO_BYTES:
        raise ValueError("Audio must be smaller than the 100 MB AnkiWeb media limit.")
    return source, extension


def _portable_media_name(source: Path, extension: str) -> str:
    stem = _SAFE_STEM_RE.sub("-", source.stem).strip("._-")
    stem = stem[:_MAX_STEM_CHARS].strip("._-") or "audio"
    return f"incremento-audio-{stem}-{uuid.uuid4().hex[:12]}{extension}"


def _add_media_file(col, source: Path, extension: str) -> str:
    desired_name = _portable_media_name(source, extension)
    with tempfile.TemporaryDirectory(prefix="incremento_audio_") as tmp_dir:
        staged = Path(tmp_dir) / desired_name
        shutil.copyfile(source, staged)
        stored_name = str(col.media.add_file(str(staged)) or "").strip()
    if not stored_name or Path(stored_name).name != stored_name:
        raise RuntimeError("Anki did not accept the audio media file.")
    return stored_name


def _stored_audio_title(title: str, attempt: int) -> str:
    base = external_plain_text(title, max_chars=2_000).strip() or "Untitled Audio"
    visible = base if attempt <= 0 else f"{base} [{attempt + 1}]"
    return external_plain_text_to_anki_html(visible, max_chars=2_050)


def audio_note_type_spec() -> NoteTypeSpec:
    return NoteTypeSpec(
        name=AUDIO_NOTE_TYPE,
        fields=(
            "Title",
            AUDIO_FIELD,
            AUDIO_FILENAME_FIELD,
            PROGRESS_KEY_FIELD,
            AUDIO_NOTES_FIELD,
            *INCREMENTO_METADATA_FIELDS,
        ),
        question_template=CARD_TEMPLATE,
        answer_template=CARD_TEMPLATE,
        normalize_field_ordinals=True,
    )


def ensure_audio_note_type(col, *, allow_existing_update: bool = False) -> None:
    ensure_note_type(
        col,
        audio_note_type_spec(),
        allow_existing_update=allow_existing_update,
    )


def add_audio_card(
    addon_dir: str,
    profile: str,
    col,
    *,
    source_path: str,
    title: str,
    deck_name: str = "Topics",
    tags: list[str] | None = None,
    notes: str = "",
) -> int:
    """Copy audio into Anki media and create a mobile-compatible topic card."""
    source, extension = _validated_source(source_path)
    stored_media = ""
    note_created = False

    with ImportOperation(addon_dir, profile, "audio") as operation:
        try:
            ensure_audio_note_type(col)
            stored_media = _add_media_file(col, source, extension)

            deck = col.decks.by_name(deck_name)
            if deck is None:
                deck_id = col.decks.add_normal_deck_with_name(deck_name).id
            else:
                deck_id = deck["id"]
            model = col.models.by_name(AUDIO_NOTE_TYPE)
            progress_key = uuid.uuid4().hex
            metadata = build_incremento_metadata(
                source_type="Audio",
                source_title=external_plain_text(title, max_chars=2_000).strip(),
                source_link=stored_media,
                content_id=operation.content_id,
            )

            for attempt in range(25):
                note = col.new_note(model)
                note["Title"] = _stored_audio_title(title, attempt)
                note[AUDIO_FIELD] = f"[sound:{stored_media}]"
                note[AUDIO_FILENAME_FIELD] = stored_media
                note[PROGRESS_KEY_FIELD] = progress_key
                note[AUDIO_NOTES_FIELD] = external_plain_text_to_anki_html(
                    notes,
                    max_chars=20_000,
                )
                apply_incremento_metadata(note, metadata)
                for tag in ["Incremento"] + [
                    value for value in (tags or []) if value != "Incremento"
                ]:
                    if not tag:
                        continue
                    if hasattr(note, "add_tag"):
                        note.add_tag(tag)
                    elif hasattr(note, "tags"):
                        note.tags.append(tag)
                note.note_type()["did"] = deck_id

                added = col.add_note(note, deck_id)
                if not added:
                    continue
                note_created = True
                cards = col.find_cards(f"nid:{note.id}")
                if not cards:
                    raise RuntimeError("Anki created the audio note without a card.")
                card_id = int(cards[0])
                operation.bind_anki(card_id=card_id, note_id=int(note.id))
                operation.commit(storage_key=stored_media)
                return card_id

            raise RuntimeError("Failed to add audio card. Anki rejected the note.")
        except Exception:
            if stored_media and not note_created:
                try:
                    col.media.trash_files([stored_media])
                except Exception:
                    pass
            raise
