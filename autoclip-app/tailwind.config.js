/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        darkBg: '#09090b',     // Nền sâu thẳm
        panelBg: '#121217',    // Nền card
        borderCol: 'rgba(255,255,255,0.08)',
        brand: '#6c63ff',      // Tím chủ đạo của bạn
        brandHover: '#8880ff',
        success: '#1fc98a',
        warning: '#f5a820',
      }
    },
  },
  plugins: [],
}