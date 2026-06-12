import React, { useState, useRef, useEffect, KeyboardEvent } from 'react';
import { X } from 'lucide-react';

interface MultiEmailInputProps {
  chips: string[];
  onChange: (chips: string[]) => void;
  suggestions?: string[];
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export function MultiEmailInput({
  chips,
  onChange,
  suggestions = [],
  placeholder = 'Add email...',
  disabled = false,
  className = '',
}: MultiEmailInputProps) {
  const [inputValue, setInputValue] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const filtered = inputValue.trim().length > 0
    ? suggestions
        .filter(s => s.toLowerCase().includes(inputValue.toLowerCase()) && !chips.includes(s))
        .slice(0, 8)
    : [];

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const commitChip = (value: string) => {
    const trimmed = value.trim().replace(/,+$/, '');
    if (trimmed && !chips.includes(trimmed)) {
      onChange([...chips, trimmed]);
    }
    setInputValue('');
    setShowDropdown(false);
    setActiveIndex(-1);
    inputRef.current?.focus();
  };

  const removeChip = (index: number) => {
    onChange(chips.filter((_, i) => i !== index));
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      // Enter/comma always commits whatever is typed as a chip
      e.preventDefault();
      if (activeIndex >= 0 && filtered[activeIndex]) {
        commitChip(filtered[activeIndex]);
      } else if (inputValue.trim()) {
        commitChip(inputValue);
      }
    } else if (e.key === 'Tab') {
      // Tab only accepts a suggestion from the dropdown — like Gmail
      // If no suggestion is showing, let Tab move focus naturally
      if (showDropdown && filtered.length > 0) {
        e.preventDefault();
        const suggestion = activeIndex >= 0 ? filtered[activeIndex] : filtered[0];
        commitChip(suggestion);
      }
      // else: no dropdown → natural Tab focus movement, do nothing
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex(i => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex(i => Math.max(i - 1, -1));
    } else if (e.key === 'Escape') {
      setShowDropdown(false);
      setActiveIndex(-1);
    } else if (e.key === 'Backspace' && inputValue === '' && chips.length > 0) {
      removeChip(chips.length - 1);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    // Auto-commit if user typed a comma
    if (val.endsWith(',')) {
      commitChip(val);
      return;
    }
    setInputValue(val);
    setShowDropdown(true);
    setActiveIndex(-1);
  };

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <div
        className={`
          flex flex-wrap items-center gap-1.5 min-h-[38px] w-full
          bg-background border border-border rounded-xl px-3 py-1.5
          focus-within:ring-2 focus-within:ring-primary/20 focus-within:border-primary
          transition-all cursor-text
          ${disabled ? 'opacity-50 pointer-events-none' : ''}
        `}
        onClick={() => inputRef.current?.focus()}
      >
        {/* Chips */}
        {chips.map((chip, i) => (
          <span
            key={chip + i}
            className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium
                       bg-primary/10 text-primary border border-primary/20
                       animate-in fade-in zoom-in-95 duration-150"
          >
            {chip}
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); removeChip(i); }}
              className="hover:bg-primary/20 rounded-full p-0.5 transition-colors"
              aria-label={`Remove ${chip}`}
            >
              <X className="w-2.5 h-2.5" />
            </button>
          </span>
        ))}

        {/* Input */}
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onFocus={() => inputValue && setShowDropdown(true)}
          placeholder={chips.length === 0 ? placeholder : ''}
          disabled={disabled}
          className="flex-1 min-w-[120px] bg-transparent outline-none text-sm placeholder:text-muted-foreground/60 py-0.5"
        />
      </div>

      {/* Autocomplete Dropdown */}
      {showDropdown && filtered.length > 0 && (
        <div className="
          absolute left-0 right-0 top-full mt-1 z-50
          bg-popover border border-border rounded-xl shadow-lg
          overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150
        ">
          {filtered.map((s, i) => (
            <button
              key={s}
              type="button"
              onMouseDown={(e) => { e.preventDefault(); commitChip(s); }}
              onMouseEnter={() => setActiveIndex(i)}
              className={`
                w-full text-left px-4 py-2 text-sm transition-colors
                ${i === activeIndex ? 'bg-primary/10 text-primary' : 'hover:bg-muted text-foreground'}
              `}
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
