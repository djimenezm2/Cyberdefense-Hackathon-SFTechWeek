/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 950: '#07090C', 900: '#0B0E13', 850: '#10141B', 800: '#151A23', 700: '#1E2530', 600: '#2A3340', 500: '#3B4656' },
        mute: { 400: '#7C8798', 300: '#A3ADBC', 200: '#CBD2DC', 100: '#E8ECF1' },
        ok: '#2BD576', warn: '#F5A524', bad: '#FF4D5E', agent: '#8FA4F5', lime: '#D7F04B',
      },
      fontFamily: {
        sans: ['"DM Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"DM Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
}
