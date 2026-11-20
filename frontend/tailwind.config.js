/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#F2A33A',
          light: '#F7C275',
          dark: '#C97F1E',
        },
        ink: {
          DEFAULT: '#16191C',
          deep: '#101418',
        },
        sand: {
          DEFAULT: '#F7F5F1',
          line: '#E6E1D8',
        },
      },
      fontFamily: {
        sans: ['Inter', 'Noto Sans SC', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
