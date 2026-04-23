/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        background: '#080c10',
        'accent-cyan': '#00e5cc',
        'accent-orange': '#ff6b35',
        danger: '#ff3355',
        'text-primary': '#c8d8e8',
      },
      fontFamily: {
        mono: ['var(--font-mono)', 'IBM Plex Mono', 'monospace'],
        syne: ['var(--font-syne)', 'Syne', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
