import React, { useState, useRef, useEffect } from 'react';
import { FaChevronDown } from 'react-icons/fa';

interface SelectDropdownOption {
  value: string;
  label: string;
  subtitle?: string;
}

interface SelectDropdownProps {
  value: string;
  onChange: (value: string) => void;
  options: SelectDropdownOption[];
  placeholder?: string;
  className?: string;
}

/**
 * SelectDropdown - DaisyUI dropdown component that works like a select
 * Uses details/summary pattern to avoid z-index issues with modals
 */
const SelectDropdown: React.FC<SelectDropdownProps> = ({
  value,
  onChange,
  options,
  placeholder = 'Select...',
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const detailsRef = useRef<HTMLDetailsElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (detailsRef.current && !detailsRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen]);

  const selectedOption = options.find((opt) => opt.value === value);

  const handleSelect = (optionValue: string) => {
    onChange(optionValue);
    setIsOpen(false);
  };

  return (
    <details
      ref={detailsRef}
      className={`dropdown dropdown-end ${isOpen ? 'dropdown-open' : ''} w-full ${className}`}
      open={isOpen}
      onToggle={(e) => setIsOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary
        className="btn btn-outline w-full justify-between font-normal cursor-pointer list-none"
        onClick={(e) => {
          e.preventDefault();
          setIsOpen(!isOpen);
        }}
      >
        {selectedOption ? (
          <div className="text-left flex-1 overflow-hidden">
            <div className="font-medium truncate">{selectedOption.label}</div>
            {selectedOption.subtitle && (
              <div className="text-xs opacity-60 truncate">{selectedOption.subtitle}</div>
            )}
          </div>
        ) : (
          <span className="opacity-50">{placeholder}</span>
        )}
        <FaChevronDown
          className={`opacity-50 transition-transform flex-shrink-0 ml-2 ${
            isOpen ? 'rotate-180' : ''
          }`}
        />
      </summary>
      <ul className="dropdown-content menu menu-compact bg-base-100 rounded-box z-[9999] w-full max-h-60 overflow-y-auto shadow-xl border border-base-300 p-1 mt-1">
        {options.map((option) => (
          <li key={option.value} className="w-full">
            <a
              className={`whitespace-normal block ${value === option.value ? 'active' : ''}`}
              onClick={(e) => {
                e.preventDefault();
                handleSelect(option.value);
              }}
            >
              <div className="w-full">
                <div className="font-medium">{option.label}</div>
                {option.subtitle && (
                  <div className="text-xs opacity-60">{option.subtitle}</div>
                )}
              </div>
            </a>
          </li>
        ))}
      </ul>
    </details>
  );
};

export default SelectDropdown;
