export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: { extend: {
    fontFamily: { sans: ['Nunito', 'Trebuchet MS', 'Arial', 'sans-serif'] },
    colors: { ink: '#27305C', cream: '#FFF8E8', violet: '#7154D8', coral: '#F77773', mint: '#4CBFA3', sky: '#5BBAEF', sun: '#FFCE60' },
    boxShadow: { card: '0 10px 0 #E5E0F5, 0 18px 35px rgba(56,39,114,.08)' },
  } },
  plugins: [],
}
