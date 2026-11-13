/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        forest: {
          50: '#F2F8F5',
          100: '#E1EFE8',
          200: '#C4DFD2',
          300: '#9BCAA4',
          400: '#52A771',
          500: '#2D8A50',
          600: '#246F40',
          700: '#1E5834',
          800: '#1B4332',
          900: '#143827',
          950: '#0B2217',
        },
        navy: {
          50: '#F8FAFC',
          100: '#F1F5F9',
          200: '#E2E8F0',
          300: '#CBD5E1',
          400: '#94A3B8',
          500: '#64748B',
          600: '#475569',
          700: '#334155',
          800: '#1E293B',
          900: '#0F172A',
          950: '#0A0F1D',
        },
        surface: {
          base: '#F4F6F8',
          card: '#FFFFFF',
          subtle: '#F8FAFC',
          border: '#E2E8F0',
          borderStrong: '#CBD5E1',
        }
      },
      fontFamily: {
        sans: ['Inter', 'IBM Plex Sans', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'IBM Plex Mono', 'Menlo', 'Monaco', 'Courier New', 'monospace'],
      }
    },
  },
  plugins: [],
}
