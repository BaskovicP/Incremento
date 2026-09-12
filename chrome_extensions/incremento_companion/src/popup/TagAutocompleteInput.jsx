import { useEffect, useMemo, useRef, useState } from "react";

import {
  applyTagSuggestion,
  getTagSuggestions,
  normalizeAvailableTags,
} from "../shared/tagAutocomplete.js";

export function TagAutocompleteInput({
  availableTags,
  disabled = false,
  id,
  onChange,
  value,
}) {
  const inputRef = useRef(null);
  const [cursor, setCursor] = useState(String(value || "").length);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const tags = useMemo(() => normalizeAvailableTags(availableTags), [availableTags]);
  const suggestions = useMemo(
    () => getTagSuggestions(tags, value, cursor),
    [cursor, tags, value]
  );
  const listboxId = `${id}-suggestions`;
  const safeActiveIndex = suggestions.length > 0
    ? Math.min(activeIndex, suggestions.length - 1)
    : 0;

  useEffect(() => {
    if (open && suggestions.length > 0) {
      document.getElementById(`${listboxId}-${safeActiveIndex}`)?.scrollIntoView({ block: "nearest" });
    }
  }, [listboxId, open, safeActiveIndex, suggestions.length]);

  function updateCursor(input) {
    setCursor(input?.selectionStart ?? String(input?.value || "").length);
  }

  function chooseSuggestion(tag) {
    const input = inputRef.current;
    const result = applyTagSuggestion(
      value,
      tag,
      input?.selectionStart ?? cursor,
      input?.selectionEnd ?? cursor
    );
    onChange(result.value);
    setCursor(result.cursor);
    setActiveIndex(0);
    setOpen(false);
    requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.setSelectionRange(result.cursor, result.cursor);
    });
  }

  function handleKeyDown(event) {
    if (event.key === "Escape" && open) {
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
      return;
    }
    if (!suggestions.length) {
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const direction = event.key === "ArrowDown" ? 1 : -1;
      setOpen(true);
      setActiveIndex((current) => {
        if (!open) {
          return direction > 0 ? 0 : suggestions.length - 1;
        }
        return (current + direction + suggestions.length) % suggestions.length;
      });
      return;
    }
    if (open && (event.key === "Enter" || event.key === "Tab")) {
      event.preventDefault();
      chooseSuggestion(suggestions[safeActiveIndex]);
    }
  }

  return (
    <div className="tag-autocomplete">
      <input
        ref={inputRef}
        id={id}
        type="text"
        role="combobox"
        aria-autocomplete="list"
        aria-controls={listboxId}
        aria-expanded={open && suggestions.length > 0}
        aria-activedescendant={open && suggestions.length > 0
          ? `${listboxId}-${safeActiveIndex}`
          : undefined}
        autoComplete="off"
        value={value}
        placeholder="tag1 tag2"
        spellCheck="false"
        disabled={disabled}
        onBlur={() => setOpen(false)}
        onChange={(event) => {
          onChange(event.target.value);
          updateCursor(event.target);
          setActiveIndex(0);
          setOpen(true);
        }}
        onClick={(event) => {
          updateCursor(event.currentTarget);
          setActiveIndex(0);
          setOpen(true);
        }}
        onFocus={(event) => {
          updateCursor(event.currentTarget);
          setOpen(true);
        }}
        onKeyDown={handleKeyDown}
        onKeyUp={(event) => updateCursor(event.currentTarget)}
        onSelect={(event) => updateCursor(event.currentTarget)}
      />
      {open && suggestions.length > 0 ? (
        <div className="tag-suggestions" id={listboxId} role="listbox">
          {suggestions.map((tag, index) => (
            <button
              className={index === safeActiveIndex ? "is-active" : ""}
              id={`${listboxId}-${index}`}
              key={tag}
              type="button"
              role="option"
              aria-selected={index === safeActiveIndex}
              tabIndex={-1}
              onMouseEnter={() => setActiveIndex(index)}
              onMouseDown={(event) => {
                event.preventDefault();
                chooseSuggestion(tag);
              }}
            >
              {tag}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
