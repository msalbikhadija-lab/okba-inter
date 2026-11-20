import App from './App.js?v=2.9';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, errorInfo) {
    console.error('React ErrorBoundary caught:', error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return React.createElement(
        'div',
        { style: { padding: '40px', textAlign: 'center', fontFamily: 'sans-serif' } },
        React.createElement('h2', { style: { color: '#e53e3e' } }, 'Une erreur est survenue dans l\'affichage.'),
        React.createElement('p', null, String(this.state.error && this.state.error.message ? this.state.error.message : this.state.error)),
        React.createElement(
          'button',
          {
            onClick: function () { window.location.reload(); },
            style: { padding: '8px 16px', background: '#3182ce', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', marginTop: '12px' }
          },
          'Recharger la page'
        )
      );
    }
    return this.props.children;
  }
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(React.createElement(ErrorBoundary, null, React.createElement(App)));
