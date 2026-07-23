/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        mcgill: {
          red:    '#C8102E',
          dark:   '#8B0000',
          light:  '#F5D6DA',
          50:     '#fef2f4',
          100:    '#fde6ea',
          200:    '#fbbdca',
          500:    '#C8102E',
          600:    '#a60d26',
          700:    '#8B0000',
          900:    '#5a0010',
        },
        primary: {
          50:  '#fef2f4',
          100: '#fde6ea',
          500: '#C8102E',
          600: '#a60d26',
          700: '#8B0000',
          800: '#6d000a',
          900: '#5a0010',
        },
        science: {
          50:  '#f0f9ff',
          500: '#0ea5e9',
          700: '#0369a1',
          900: '#0c4a6e',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
