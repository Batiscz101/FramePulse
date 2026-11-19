/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        canvas: '#09090B',
        surface: '#121215',
        hairline: '#27272A',
        ink: '#FAFAFA',
        muted: '#A1A1AA',
        faint: '#71717A',
        accent: '#9BC7B2',
        danger: '#F87171',
      },
    },
  },
  plugins: [],
};
