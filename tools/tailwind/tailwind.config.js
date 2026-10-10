module.exports = Object.assign({
  content: ['../../web_studio/index.html', '../../web_studio/download/AURA-REC.html'],
}, {
      darkMode: 'class',
      theme: {
        extend: {
          fontFamily: {
            display: ['Syne', 'sans-serif'],
            mono: ['"JetBrains Mono"', 'monospace'],
            sans: ['Inter', 'sans-serif'],
          },
          colors: {
            obsidian: {
              950: '#060709',
              900: '#0A0C10',
              850: '#0F1218',
              800: '#151922',
              700: '#1E2330',
              600: '#2A3244',
            },
            aura: {
              cyan: '#00F0FF',
              emerald: '#00FF9D',
              violet: '#8A2BE2',
              rose: '#FF2A6D',
              amber: '#FFB800',
            }
          },
          animation: {
            'pulse-glow': 'pulseGlow 2.5s infinite ease-in-out',
            'border-flow': 'borderFlow 4s linear infinite',
          },
          keyframes: {
            pulseGlow: {
              '0%, 100%': { opacity: '0.4', transform: 'scale(1)' },
              '50%': { opacity: '0.8', transform: 'scale(1.04)' },
            },
            borderFlow: {
              '0%': { backgroundPosition: '0% 50%' },
              '100%': { backgroundPosition: '200% 50%' },
            }
          }
        }
      }
    });
