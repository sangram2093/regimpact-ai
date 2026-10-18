import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { TextSizeControl } from '../components/TextSizeControl';

const scale = () => document.documentElement.style.getPropertyValue('--text-scale');

describe('TextSizeControl', () => {
  afterEach(() => {
    localStorage.clear();
    document.documentElement.style.removeProperty('--text-scale');
  });

  it('enlarges text, remembers the choice and resets', () => {
    render(<TextSizeControl />);
    expect(scale()).toBe('1');
    expect(screen.getByRole('button', { name: 'Smaller text' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Larger text' }));
    fireEvent.click(screen.getByRole('button', { name: 'Larger text' }));
    expect(scale()).toBe('1.25');
    expect(localStorage.getItem('regimpact-text-scale')).toBe('2');

    fireEvent.click(screen.getByRole('button', { name: /Reset text size/ }));
    expect(scale()).toBe('1');
  });

  it('restores a saved size', () => {
    localStorage.setItem('regimpact-text-scale', '3');
    render(<TextSizeControl />);
    expect(scale()).toBe('1.375');
    expect(screen.getByRole('button', { name: 'Larger text' })).toBeDisabled();
  });
});
