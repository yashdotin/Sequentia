module.exports = {
  content: ["./templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        void: '#0a0e1c',
        surface: '#12172a',
        'surface-2': '#1a2140',
        edge: '#232b48',
        ink: '#f4f6fc',
        'ink-muted': '#8891b3',
        'ink-faint': '#5c6488',
        system: '#4d7cfe',
        'system-dim': '#2c4ba0',
        signal: '#ff9142',
        'signal-dim': '#a85f2b',
        verified: '#35d399',
        locked: '#4a5170',
        warn: '#f2c14e',
        // legacy aliases — old templates not yet migrated to the new tokens
        // still resolve to sensible equivalents. remove once every template
        // in the redesign phases has been touched.
        navy: '#0a0e1c',
        panel: '#12172a',
        electric: '#4d7cfe',
        violet: '#7c3aed',
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'sans-serif'],
        body: ['Inter', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
      },
      borderRadius: {
        card: '1.25rem',
        modal: '1.5rem',
      },
      keyframes: {
        'pulse-thread': {
          '0%, 100%': { opacity: 0.35 },
          '50%': { opacity: 1 },
        },
        'thread-travel': {
          '0%': { backgroundPosition: '0% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        rise: {
          '0%': { opacity: 0, transform: 'translateY(6px)' },
          '100%': { opacity: 1, transform: 'translateY(0)' },
        },
      },
      animation: {
        'pulse-thread': 'pulse-thread 2.2s ease-in-out infinite',
        'thread-travel': 'thread-travel 3s linear infinite',
        rise: 'rise 0.3s ease-out',
      },
    }
  },
  plugins: [],
}
