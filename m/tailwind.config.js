/** @type {import('tailwindcss').Config} */

// Semantic colours resolve through CSS variables so the whole UI can switch
// between the dark and light palettes at runtime (see src/lib/theme.ts).
const color = (name) => `rgb(var(--color-${name}) / <alpha-value>)`;

module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        canvas: color('canvas'),
        surface: color('surface'),
        raised: color('raised'),
        hairline: color('hairline'),
        ink: color('ink'),
        muted: color('muted'),
        faint: color('faint'),
        accent: color('accent'),
        grid: color('grid'),
        strip: color('strip'),
        tooltip: color('tooltip'),
        'tooltip-border': color('tooltip-border'),
        danger: color('danger'),
        'on-ink-muted': color('on-ink-muted'),
      },
    },
  },
  plugins: [
    // Dark defaults for the very first render before the provider mounts.
    ({ addBase }) =>
      addBase({
        ':root': {
          '--color-canvas': '9 9 11',
          '--color-surface': '18 18 21',
          '--color-raised': '24 24 28',
          '--color-hairline': '39 39 42',
          '--color-ink': '250 250 250',
          '--color-muted': '161 161 170',
          '--color-faint': '113 113 122',
          '--color-accent': '155 199 178',
          '--color-grid': '30 30 34',
          '--color-strip': '63 63 70',
          '--color-tooltip': '28 28 32',
          '--color-tooltip-border': '63 63 70',
          '--color-danger': '248 113 113',
          '--color-on-ink-muted': '82 82 91',
        },
      }),
  ],
};
