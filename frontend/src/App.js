const { useEffect, useState } = React;
const e = React.createElement;

const configuredApiUrl =
  document.querySelector('meta[name="okba-api-url"]')?.content.trim();
const API_URL =
  configuredApiUrl && !configuredApiUrl.startsWith('__')
    ? configuredApiUrl
    : (typeof window !== 'undefined' &&
       window.location &&
       (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
        ? 'http://localhost:5100/api'
        : '/api');
const VIEW_PERMISSIONS = {
  clients: 'client',
  articles: 'article',
  suppliers: 'fournisseur',
  'module:vehicles': 'voiture',
  'module:fairs': 'foire',
  'module:fair-assignments': 'foire',
  'module:fair-inventory': 'foire',
  'module:reservations': 'reservation',
  'module:stand-types': 'liste_stand',
  'module:stand-inventory': 'stand',
  'module:works': 'work',
  'module:permissions': 'empl',
  'module:employees': 'empl',
};
const USER_NAVIGATION = [
  ['clients', 'Clients', 'client'],
  ['articles', 'Articles', 'article'],
  ['stock', 'Stock', ['mouvement', 'reception', 'achat', 'livraison', 'vente']],
  ['suppliers', 'Fournisseurs', 'fournisseur'],
  ['pos', 'Caisse', 'vente'],
  ['module:fairs', 'Foires', 'foire'],
  ['module:fair-assignments', 'Équipe des foires', 'foire'],
  ['module:fair-inventory', 'Stock des foires', 'foire'],
  ['module:reservations', 'Réservations', 'reservation'],
  ['module:vehicles', 'Véhicules', 'voiture'],
  ['module:stand-types', 'Types de stands', 'liste_stand'],
  ['module:stand-inventory', 'Articles des stands', 'stand'],
  ['module:works', 'Missions', 'work'],
  ['module:permissions', 'Droits', 'empl'],
  ['module:employees', 'Employés', 'empl'],
];
const FAIR_STATUSES = [
  ['', 'Non défini'],
  ['planned', 'À venir'],
  ['active', 'En cours'],
  ['completed', 'Terminée'],
  ['cancelled', 'Annulée'],
];

function hasViewPermission(user, required) {
  if (!user) return false;
  if (user.type === 'admin') return true;
  const fields = Array.isArray(required) ? required : [required];
  return fields.some((field) => user.permissions?.[field] === true);
}

function canAccessView(user, view) {
  if (!user) return false;
  if (user.type === 'admin') return true;
  if (view === 'home') return true;
  if (view === 'users') return false;
  if (view === 'stock') {
    return hasViewPermission(user, USER_NAVIGATION.find(([key]) => key === 'stock')[2]);
  }
  if (view === 'pos') return hasViewPermission(user, 'vente');
  return hasViewPermission(user, VIEW_PERMISSIONS[view]);
}

const MOVEMENT_PERMISSION = {
  reception: 'reception',
  achat: 'achat',
  livraison: 'livraison',
  vente: 'vente',
};

function canManageMovement(user, movementType) {
  return hasViewPermission(user, MOVEMENT_PERMISSION[movementType]);
}

const ROLES = [
  ['admin', 'Administrateur'],
  ['chauffeur', 'Chauffeur'],
  ['chef', 'Chef'],
  ['vendeur', 'Vendeur'],
  ['deco', 'Décorateur'],
  ['reservation', 'Réservation'],
  ['laga', 'Laga'],
  ['compta', 'Comptabilité'],
];
const EMPTY_FORM = {
  nom: '',
  prenom: '',
  login: '',
  password: '',
  type: 'vendeur',
  lpp: '8',
  ville: '',
};

async function api(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || 'Une erreur est survenue.');
  }
  return data;
}

function App() {
  const [user, setUser] = useState(null);
  const [currency, setCurrency] = useState('TND');
  const [activeView, setActiveView] = useState('dashboard');
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
const [search, setSearch] = useState('');

  async function refreshUsers() {
    const data = await api('/users');
    setUsers(data);
  }

  async function refreshSettings() {
    const data = await api('/settings');
    setCurrency(data.currency);
  }

  useEffect(() => {
    api('/me')
      .then(async ({ user: currentUser }) => {
        setUser(currentUser);
        await refreshSettings().catch((requestError) => setError(requestError.message));
        if (currentUser.type === 'admin') {
          return refreshUsers();
        }
      })
      .catch((requestError) => {
        if (requestError.message !== 'Authentification requise') {
          setError(requestError.message);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (user && !canAccessView(user, activeView)) {
      setActiveView(user.type === 'admin' ? 'dashboard' : 'home');
    }
  }, [user, activeView]);

  async function login(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    setMessage('');
    const formData = new FormData(event.currentTarget);

    try {
      const data = await api('/login', {
        method: 'POST',
        body: JSON.stringify({
          login: formData.get('login'),
          password: formData.get('password'),
        }),
      });
      setUser(data.user);
      setActiveView(data.user.type === 'admin' ? 'dashboard' : 'home');
      await refreshSettings().catch((requestError) => setError(requestError.message));
      if (data.user.type === 'admin') {
        await refreshUsers();
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function logout() {
    setError('');
    try {
      await api('/logout', { method: 'POST' });
      setUser(null);
      setUsers([]);
      setEditingId(null);
      setForm(EMPTY_FORM);
      setMessage('');
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  function startEdit(selectedUser) {
    setEditingId(selectedUser.id);
    setForm({
      nom: selectedUser.nom,
      prenom: selectedUser.prenom,
      login: selectedUser.login,
      password: '',
      type: selectedUser.type,
      lpp: String(selectedUser.lpp),
      ville: selectedUser.ville || '',
    });
    setMessage('');
    setError('');
  }

  function resetForm() {
    setEditingId(null);
    setForm(EMPTY_FORM);
  }

  async function saveUser(event) {
    event.preventDefault();
    setSaving(true);
    setError('');
    setMessage('');
    const formData = new FormData(event.currentTarget);
    const payload = {
      nom: formData.get('nom'),
      prenom: formData.get('prenom'),
      login: formData.get('login'),
      type: formData.get('type'),
      lpp: Number(formData.get('lpp')),
      ville: formData.get('ville'),
    };
    const password = formData.get('password');
    if (password) {
      payload.password = password;
    }

    try {
      const path = editingId ? `/users/${editingId}` : '/users';
      const data = await api(path, {
        method: editingId ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      });
      setMessage(data.message);
      resetForm();
      await refreshUsers();
      if (user.id === editingId) {
        const { user: currentUser } = await api('/me');
        setUser(currentUser);
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function deleteUser(selectedUser) {
    if (!window.confirm(`Supprimer le compte de ${selectedUser.prenom} ${selectedUser.nom} ?`)) {
      return;
    }
    setError('');
    setMessage('');
    try {
      const data = await api(`/users/${selectedUser.id}`, { method: 'DELETE' });
      setMessage(data.message);
      await refreshUsers();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  if (loading) {
    return e('main', { className: 'login-page' }, e('p', null, 'Chargement...'));
  }

  if (user && activeView === 'dashboard' && user.type === 'admin') {
    return e(DashboardPage, {
      user,
      currency,
      onNavigate: setActiveView,
      onLogout: logout,
    });
  }

  if (user && activeView === 'alerts') {
    return e(AlertsPage, {
      user,
      currency,
      onNavigate: setActiveView,
      onLogout: logout,
    });
  }

  if (user && activeView === 'clients' && canAccessView(user, activeView)) {
    return e(ClientsPage, {
      user,
      onBack: () => setActiveView('users'),
      onArticles: () => setActiveView('articles'),
      onLogout: logout,
    });
  }

  if (user && activeView === 'articles' && canAccessView(user, activeView)) {
    return e(ArticlesPage, {
      user,
      onBack: () => setActiveView(user.type === 'admin' ? 'dashboard' : 'home'),
      onClients: () => setActiveView('clients'),
      onStock: () => setActiveView('stock'),
      onLogout: logout,
    });
  }

  if (user && activeView === 'stock' && canAccessView(user, activeView)) {
    return e(StockPage, {
      user,
      onBack: () => setActiveView(user.type === 'admin' ? 'dashboard' : 'home'),
      onArticles: () => setActiveView('articles'),
      onSuppliers: () => setActiveView('suppliers'),
      onLogout: logout,
    });
  }

  if (user && activeView === 'suppliers' && canAccessView(user, activeView)) {
    return e(SuppliersPage, {
      user,
      onBack: () => setActiveView(user.type === 'admin' ? 'dashboard' : 'home'),
      onStock: () => setActiveView('stock'),
      onLogout: logout,
    });
  }

  if (user && activeView === 'pos' && canAccessView(user, activeView)) {
    return e(POSPage, {
      user,
      currency,
      onBack: () => setActiveView(user.type === 'admin' ? 'dashboard' : 'home'),
      onLogout: logout,
    });
  }

  if (user && activeView === 'module:settings' && user.type === 'admin') {
    return e(SystemSettingsPage, {
      user,
      currency,
      onCurrencyChange: setCurrency,
      onNavigate: setActiveView,
      onLogout: logout,
    });
  }

  if (
    user &&
    activeView === 'module:fair-assignments' &&
    canAccessView(user, activeView)
  ) {
    return e(FairAssignmentsPage, {
      user,
      onNavigate: setActiveView,
      onLogout: logout,
    });
  }

  if (
    user &&
    activeView === 'module:fair-inventory' &&
    canAccessView(user, activeView)
  ) {
    return e(FairInventoryPage, {
      user,
      onNavigate: setActiveView,
      onLogout: logout,
    });
  }

  if (
    user &&
    activeView === 'module:permissions' &&
    canAccessView(user, activeView)
  ) {
    return e(ModulePage, {
      user,
      resource: 'permissions',
      onNavigate: setActiveView,
      onLogout: logout,
    });
  }

  if (
    user &&
    activeView.startsWith('module:') &&
    canAccessView(user, activeView)
  ) {
    return e(ModulePage, {
      user,
      resource: activeView.slice('module:'.length),
      onNavigate: setActiveView,
      onLogout: logout,
    });
  }

  if (!user) {
    return e(
      'main',
      { className: 'login-page' },
      e(
        'section',
        { className: 'login-box' },
        e('p', { className: 'eyebrow' }, 'ESPACE DE GESTION'),
        e('h1', null, 'OKBA INTER'),
        e('p', { className: 'subtitle' }, 'Connectez-vous pour accéder à votre espace.'),
        e(
          'form',
          { onSubmit: login },
          e(
            'label',
            null,
            'Nom de connexion',
            e('input', { name: 'login', autoComplete: 'username', required: true })
          ),
          e(
            'label',
            null,
            'Mot de passe',
            e('input', {
              name: 'password',
              type: 'password',
              autoComplete: 'current-password',
              required: true,
            })
          ),
          e(
            'button',
            { type: 'submit', className: 'button', disabled: loading },
            loading ? 'Connexion...' : 'Se connecter'
          )
        ),
        error ? e('p', { className: 'notice error', role: 'alert' }, error) : null,
        e(
          'div',
          {
            style: {
              marginTop: '24px',
              paddingTop: '16px',
              borderTop: '1px solid #334155',
              textAlign: 'center',
            },
          },
          e(
            'a',
            {
              href: './OKBA-Inter.apk',
              download: 'OKBA-Inter.apk',
              className: 'button secondary',
              style: {
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                width: '100%',
                textDecoration: 'none',
                boxSizing: 'border-box',
                padding: '10px 16px',
                fontSize: '14px',
              },
            },
            '📲 Télécharger l\'application Android (APK)'
          ),
          e(
            'p',
            {
              style: {
                marginTop: '12px',
                fontSize: '12px',
                color: '#94a3b8',
                lineHeight: '1.4',
              },
            },
            '🍏 Sur iPhone : dans Safari, appuyez sur ',
            e('strong', { style: { color: '#f8fafc' } }, 'Partager ⎋'),
            ' puis sur ',
            e('strong', { style: { color: '#f8fafc' } }, '« Sur l\'écran d\'accueil »'),
            ' pour l\'installer comme une application native.'
          )
        )
      )
    );
  }

  const availableNavigation = USER_NAVIGATION.filter(([, , permission]) =>
    hasViewPermission(user, permission)
  );

  if (user.type !== 'admin') {
    return e(
      'main',
      { className: 'dashboard' },
      e(
        'header',
        { className: 'topbar' },
        e('strong', null, 'OKBA INTER'),
        e(
          'div',
          { className: 'topbar-user' },
            ...availableNavigation.map(([view, label]) =>
              e('button', { key: view, className: 'button secondary small-button', onClick: () => setActiveView(view) }, label)
            ),
            e('button', { className: 'button secondary small-button', onClick: logout }, 'Déconnexion')
        )
      ),
      e(
        'section',
        { className: 'welcome-card' },
        e('p', { className: 'eyebrow' }, 'ESPACE UTILISATEUR'),
        e('h1', null, `Bienvenue ${user.prenom} ${user.nom}`),
        e('p', null, `Votre rôle : ${ROLES.find(([role]) => role === user.type)?.[1] || user.type}`),
        e(
          'div',
          { className: 'welcome-actions' },
          ...availableNavigation.map(([view, label], index) =>
            e('button', {
              key: view,
              className: `button${index ? ' secondary' : ''}`,
              onClick: () => setActiveView(view),
            }, `Ouvrir ${label.toLowerCase()}`)
          )
        ),
        availableNavigation.length
          ? e('p', { className: 'subtitle' }, 'Modules disponibles selon les droits attribués à votre rôle.')
          : e('p', { className: 'notice error', role: 'status' }, 'Aucun module ne vous est attribué. Contactez un administrateur.')
      ),
      error ? e('p', { className: 'notice error' }, error) : null
    );
  }

  const filteredUsers = users.filter((item) => {
    const searchable = `${item.nom} ${item.prenom} ${item.login} ${item.type} ${item.ville || ''}`.toLowerCase();
    return searchable.includes(search.toLowerCase());
  });



  return e(
    'main',
    { className: 'dashboard' },

    e(
      'header',
      { className: 'topbar' },
      e(
        'div',
        null,
        e('strong', null, 'OKBA INTER'),
        e('span', { className: 'topbar-label' }, 'Administration')
      ),
      e(
        'div',
        { className: 'topbar-user' },
        e('span', null, `${user.prenom} ${user.nom}`),
        e('button', { className: 'button small-button', onClick: () => setActiveView('dashboard') }, '\uD83D\uDCCA Dashboard'),
        e('button', { className: 'button secondary small-button', onClick: () => setActiveView('clients') }, 'Clients'),
        e('button', { className: 'button secondary small-button', onClick: () => setActiveView('articles') }, 'Articles'),
        e('button', { className: 'button secondary small-button', onClick: () => setActiveView('stock') }, 'Stock'),
        e('button', { className: 'button secondary small-button', onClick: () => setActiveView('pos') }, 'Caisse'),
        e('button', { className: 'button secondary small-button', onClick: () => setActiveView('suppliers') }, 'Fournisseurs'),
        e('button', { className: 'button secondary small-button', onClick: () => setActiveView('module:fairs') }, 'Foires'),
        e('button', { className: 'button secondary small-button', onClick: () => setActiveView('module:fair-assignments') }, 'Équipe des foires'),
        e('button', { className: 'button secondary small-button', onClick: () => setActiveView('module:fair-inventory') }, 'Stock des foires'),
        e('button', { className: 'button secondary small-button', onClick: () => setActiveView('module:reservations') }, 'Réservations'),
        e('button', { className: 'button secondary small-button', onClick: () => setActiveView('module:vehicles') }, 'Véhicules'),
        e('button', { className: 'button secondary small-button', onClick: () => setActiveView('module:stand-types') }, 'Stands'),
        e('button', { className: 'button secondary small-button', onClick: () => setActiveView('module:stand-inventory') }, 'Articles des stands'),
        e('button', { className: 'button secondary small-button', onClick: () => setActiveView('module:works') }, 'Missions'),
        e('button', { className: 'button secondary small-button', onClick: () => setActiveView('module:permissions') }, 'Droits'),
        e('button', { className: 'button secondary small-button', onClick: () => setActiveView('module:settings') }, 'Paramètres'),
        e('button', { className: 'button secondary small-button', onClick: logout }, 'Déconnexion')
      )
    ),
    e(
      'div',
      { className: 'content' },
      e(
        'div',
        { className: 'page-heading' },
        e(
          'div',
          null,
          e('p', { className: 'eyebrow' }, 'ADMINISTRATION'),
          e('h1', null, 'Utilisateurs et rôles'),
          e('p', { className: 'subtitle' }, 'Créez et gérez les comptes d’accès de l’application.')
        ),
        e('span', { className: 'count-badge' }, `${users.length} compte${users.length === 1 ? '' : 's'}`)
      ),
      message ? e('p', { className: 'notice success', role: 'status' }, message) : null,
      error ? e('p', { className: 'notice error', role: 'alert' }, error) : null,
      e(
        'div',
        { className: 'admin-grid' },
        e(
          'section',
          { className: 'panel' },
          e('div', { className: 'panel-heading' }, e('h2', null, 'Comptes'), e('span', null, `${filteredUsers.length} affiché(s)`)),
          e('input', {
            className: 'search-input',
            type: 'search',
            placeholder: 'Rechercher un utilisateur...',
            value: search,
            onChange: (event) => setSearch(event.target.value),
            'aria-label': 'Rechercher un utilisateur',
          }),
          e(
            'div',
            { className: 'table-wrap' },
            e(
              'table',
              null,
              e(
                'thead',
                null,
                e('tr', null, e('th', null, 'Utilisateur'), e('th', null, 'Identifiant'), e('th', null, 'Rôle'), e('th', null, 'Ville'), e('th', null, 'Actions'))
              ),
              e(
                'tbody',
                null,
                filteredUsers.length
                  ? filteredUsers.map((item) =>
                      e(
                        'tr',
                        { key: item.id },
                        e(
                          'td',
                          null,
                          e('strong', null, `${item.prenom} ${item.nom}`),
                          e('span', { className: 'cell-detail' }, `ID ${item.id}`)
                        ),
                        e('td', null, item.login),
                        e(
                          'td',
                          null,
                          e('span', { className: 'role-badge' }, ROLES.find(([role]) => role === item.type)?.[1] || item.type)
                        ),
                        e('td', null, item.ville || '—'),
                        e(
                          'td',
                          { className: 'actions-cell' },
                          e('button', { className: 'text-button', onClick: () => startEdit(item) }, 'Modifier'),
                          item.id !== user.id
                            ? e('button', { className: 'text-button danger-text', onClick: () => deleteUser(item) }, 'Supprimer')
                            : null
                        )
                      )
                    )
                  : e('tr', null, e('td', { className: 'empty-state', colSpan: 5 }, 'Aucun utilisateur trouvé.'))
              )
            )
          )
        ),
        e(
          'section',
          { className: 'panel form-panel' },
          e(
            'div',
            { className: 'panel-heading' },
            e('h2', null, editingId ? 'Modifier le compte' : 'Ajouter un compte'),
            editingId ? e('button', { className: 'text-button', onClick: resetForm }, 'Annuler') : null
          ),
          e(
            'form',
            { onSubmit: saveUser },
            e(
              'div',
              { className: 'form-row' },
              e(
                'label',
                null,
                'Prénom',
                e('input', {
                  name: 'prenom',
                  value: form.prenom,
                  onChange: (event) => setForm({ ...form, prenom: event.target.value }),
                  required: true,
                })
              ),
              e(
                'label',
                null,
                'Nom',
                e('input', {
                  name: 'nom',
                  value: form.nom,
                  onChange: (event) => setForm({ ...form, nom: event.target.value }),
                  required: true,
                })
              )
            ),
            e(
              'label',
              null,
              'Ville',
              e('input', {
                name: 'ville',
                value: form.ville,
                onChange: (event) => setForm({ ...form, ville: event.target.value }),
                maxLength: 100,
              })
            ),
            e(
              'label',
              null,
              'Nom de connexion',
              e('input', {
                name: 'login',
                value: form.login,
                onChange: (event) => setForm({ ...form, login: event.target.value }),
                autoComplete: 'off',
                required: true,
              })
            ),
            e(
              'label',
              null,
              editingId ? 'Nouveau mot de passe (facultatif)' : 'Mot de passe',
              e('input', {
                name: 'password',
                type: 'password',
                value: form.password,
                onChange: (event) => setForm({ ...form, password: event.target.value }),
                autoComplete: 'new-password',
                minLength: 8,
                required: !editingId,
              })
            ),
            e(
              'div',
              { className: 'form-row' },
              e(
                'label',
                null,
                'Rôle',
                e(
                  'select',
                  {
                    name: 'type',
                    value: form.type,
                    onChange: (event) => setForm({ ...form, type: event.target.value }),
                  },
                  ROLES.map(([value, label]) => e('option', { key: value, value }, label))
                )
              ),
              e(
                'label',
                null,
                'Lignes par page',
                e('input', {
                  name: 'lpp',
                  type: 'number',
                  min: 1,
                  max: 100,
                  value: form.lpp,
                  onChange: (event) => setForm({ ...form, lpp: event.target.value }),
                  required: true,
                })
              )
            ),
            e(
              'button',
              { type: 'submit', className: 'button', disabled: saving },
              saving ? 'Enregistrement...' : editingId ? 'Enregistrer les changements' : 'Créer le compte'
            )
          )
        )
      ),
    )
  );
}

export default App;

// ---------------------------------------------------------------------------
// Dashboard Page (Admin)
// ---------------------------------------------------------------------------

function DashboardPage({ user, currency, onNavigate, onLogout }) {
  const [data, setData] = useState(null);
  const [alerts, setAlerts] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(function () {
    Promise.all([
      api('/dashboard'),
      api('/alerts'),
    ])
      .then(function (results) {
        setData(results[0]);
        setAlerts(results[1]);
      })
      .catch(function (err) { setError(err.message); })
      .finally(function () { setLoading(false); });
  }, []);

  function kpiCard(label, value, color) {
    return e(
      'div',
      { className: 'kpi-card', style: { borderLeft: '4px solid ' + color, padding: '16px', background: '#fff', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,.1)' } },
      e('p', { style: { margin: '0 0 4px', fontSize: '13px', color: '#666' } }, label),
      e('p', { style: { margin: 0, fontSize: '24px', fontWeight: 700 } }, String(value))
    );
  }

  var alertTotal = alerts && alerts.counts
    ? alerts.counts.low_stock + alerts.counts.overdue + alerts.counts.upcoming_fairs + alerts.counts.unconfigured
    : 0;

  return e(
    'main',
    { className: 'dashboard' },
    e(
      'header',
      { className: 'topbar' },
      e(
        'div',
        null,
        e('strong', null, 'OKBA INTER'),
        e('span', { className: 'topbar-label' }, 'Tableau de bord')
      ),
      e(
        'div',
        { className: 'topbar-user' },
        e('span', null, user.prenom + ' ' + user.nom),
        alertTotal > 0
          ? e(
              'button',
              {
                className: 'button secondary small-button',
                style: { position: 'relative' },
                onClick: function () { onNavigate('alerts'); },
              },
              '\uD83D\uDD14',
              e('span', {
                style: {
                  position: 'absolute', top: '-6px', right: '-6px',
                  background: '#e53e3e', color: '#fff', borderRadius: '50%',
                  width: '18px', height: '18px', fontSize: '11px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                },
              }, String(alertTotal))
            )
          : null,
        e('button', { className: 'button secondary small-button', onClick: function () { onNavigate('users'); } }, 'Utilisateurs'),
        e('button', { className: 'button secondary small-button', onClick: function () { onNavigate('module:settings'); } }, 'Param\u00e8tres'),
        e('button', { className: 'button secondary small-button', onClick: onLogout }, 'D\u00e9connexion')
      )
    ),
    e(
      'div',
      { className: 'content' },
      e(
        'div',
        { className: 'page-heading' },
        e(
          'div',
          null,
          e('p', { className: 'eyebrow' }, 'TABLEAU DE BORD'),
          e('h1', null, 'Bienvenue ' + user.prenom),
          e('p', { className: 'subtitle' }, 'Vue d\'ensemble de votre activit\u00e9 commerciale.')
        )
      ),
      error ? e('p', { className: 'notice error', role: 'alert' }, error) : null,
      loading
        ? e('p', null, 'Chargement du tableau de bord...')
        : data
        ? e(
            React.Fragment,
            null,
            e(
              'div',
              { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px' } },
              kpiCard('Articles', data.total_articles, '#3182ce'),
              kpiCard('Clients', data.total_clients, '#38a169'),
              kpiCard('Fournisseurs', data.total_suppliers, '#d69e2e'),
              kpiCard('Utilisateurs', data.total_users, '#805ad5'),
              kpiCard('Ventes aujourd\'hui', data.today_sales_count + ' (' + data.today_sales_amount + ' ' + (currency || 'TND') + ')', '#e53e3e'),
              kpiCard('Ventes semaine', data.week_sales_amount + ' ' + (currency || 'TND'), '#dd6b20'),
              kpiCard('Ventes mois', data.month_sales_amount + ' ' + (currency || 'TND'), '#319795'),
              kpiCard('Cr\u00e9ances', data.total_receivables + ' ' + (currency || 'TND'), data.total_receivables !== '0.00' ? '#e53e3e' : '#38a169'),
              kpiCard('Foires actives', data.active_fairs, '#3182ce'),
              kpiCard('Foires \u00e0 venir', data.upcoming_fairs, '#805ad5'),
              kpiCard('Stock faible', data.low_stock_articles, data.low_stock_articles > 0 ? '#e53e3e' : '#38a169'),
              kpiCard('Produits non configur\u00e9s', data.unconfigured_products, data.unconfigured_products > 0 ? '#dd6b20' : '#38a169')
            ),
            e(
              'div',
              { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: '24px', marginBottom: '24px' } },
              e(
                'section',
                { className: 'panel' },
                e('div', { className: 'panel-heading' }, e('h2', null, 'Top 5 produits vendus')),
                e(
                  'div',
                  { className: 'table-wrap' },
                  e(
                    'table',
                    null,
                    e('thead', null, e('tr', null,
                      e('th', null, 'Code'),
                      e('th', null, 'D\u00e9signation'),
                      e('th', { style: { textAlign: 'right' } }, 'Qt\u00e9 vendue')
                    )),
                    e('tbody', null,
                      ...(data.top_products || []).map(function (p, i) {
                        return e('tr', { key: i },
                          e('td', null, p.product_code),
                          e('td', null, p.gen_name),
                          e('td', { style: { textAlign: 'right' } }, String(p.qty_sold))
                        );
                      }),
                      data.top_products && data.top_products.length === 0
                        ? e('tr', null, e('td', { colSpan: 3, style: { textAlign: 'center', color: '#999' } }, 'Aucune donn\u00e9e'))
                        : null
                    )
                  )
                )
              ),
              e(
                'section',
                { className: 'panel' },
                e('div', { className: 'panel-heading' }, e('h2', null, '5 derni\u00e8res ventes')),
                e(
                  'div',
                  { className: 'table-wrap' },
                  e(
                    'table',
                    null,
                    e('thead', null, e('tr', null,
                      e('th', null, 'N\u00b0 Facture'),
                      e('th', null, 'Date'),
                      e('th', null, 'Caissier'),
                      e('th', { style: { textAlign: 'right' } }, 'Montant')
                    )),
                    e('tbody', null,
                      ...(data.recent_sales || []).map(function (s, i) {
                        return e('tr', { key: i },
                          e('td', null, s.invoice_number),
                          e('td', null, s.date),
                          e('td', null, s.cashier),
                          e('td', { style: { textAlign: 'right' } }, s.amount + ' ' + (currency || 'TND'))
                        );
                      }),
                      data.recent_sales && data.recent_sales.length === 0
                        ? e('tr', null, e('td', { colSpan: 4, style: { textAlign: 'center', color: '#999' } }, 'Aucune vente'))
                        : null
                    )
                  )
                )
              )
            ),
            e(
              'div',
              { style: { display: 'flex', flexWrap: 'wrap', gap: '8px' } },
              e('button', { className: 'button', onClick: function () { onNavigate('pos'); } }, '\uD83D\uDED2 Caisse'),
              e('button', { className: 'button secondary', onClick: function () { onNavigate('articles'); } }, '\uD83D\uDCE6 Articles'),
              e('button', { className: 'button secondary', onClick: function () { onNavigate('clients'); } }, '\uD83D\uDC65 Clients'),
              e('button', { className: 'button secondary', onClick: function () { onNavigate('stock'); } }, '\uD83D\uDCCA Stock'),
              e('button', { className: 'button secondary', onClick: function () { onNavigate('suppliers'); } }, '\uD83C\uDFED Fournisseurs'),
              e('button', { className: 'button secondary', onClick: function () { onNavigate('module:fairs'); } }, '\uD83C\uDFAA Foires'),
              e('button', { className: 'button secondary', onClick: function () { onNavigate('users'); } }, '\uD83D\uDC64 Utilisateurs'),
              e('button', { className: 'button secondary', onClick: function () { onNavigate('module:settings'); } }, '\u2699\uFE0F Param\u00e8tres')
            )
          )
        : null
    )
  );
}


// ---------------------------------------------------------------------------
// Alerts Page
// ---------------------------------------------------------------------------

function AlertsPage({ user, currency, onNavigate, onLogout }) {
  const [alerts, setAlerts] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(function () {
    api('/alerts')
      .then(setAlerts)
      .catch(function (err) { setError(err.message); })
      .finally(function () { setLoading(false); });
  }, []);

  return e(
    'main',
    { className: 'dashboard' },
    e(
      'header',
      { className: 'topbar' },
      e(
        'div',
        null,
        e('strong', null, 'OKBA INTER'),
        e('span', { className: 'topbar-label' }, 'Alertes')
      ),
      e(
        'div',
        { className: 'topbar-user' },
        e('span', null, user.prenom + ' ' + user.nom),
        e('button', { className: 'button secondary small-button', onClick: function () { onNavigate(user.type === 'admin' ? 'dashboard' : 'home'); } }, '\u2190 Retour'),
        e('button', { className: 'button secondary small-button', onClick: onLogout }, 'D\u00e9connexion')
      )
    ),
    e(
      'div',
      { className: 'content' },
      e(
        'div',
        { className: 'page-heading' },
        e(
          'div',
          null,
          e('p', { className: 'eyebrow' }, 'NOTIFICATIONS'),
          e('h1', null, 'Alertes'),
          e('p', { className: 'subtitle' }, 'Stock faible, cr\u00e9ances en retard, foires \u00e0 venir.')
        )
      ),
      error ? e('p', { className: 'notice error', role: 'alert' }, error) : null,
      loading
        ? e('p', null, 'Chargement des alertes...')
        : alerts
        ? e(
            React.Fragment,
            null,
            alerts.low_stock && alerts.low_stock.length > 0
              ? e(
                  'section',
                  { className: 'panel', style: { marginBottom: '16px' } },
                  e('div', { className: 'panel-heading' },
                    e('h2', null, '\u26A0\uFE0F Stock faible (' + alerts.counts.low_stock + ')')
                  ),
                  e(
                    'div',
                    { className: 'table-wrap' },
                    e(
                      'table',
                      null,
                      e('thead', null, e('tr', null,
                        e('th', null, 'R\u00e9f\u00e9rence'),
                        e('th', null, 'Nom'),
                        e('th', { style: { textAlign: 'right' } }, 'Stock')
                      )),
                      e('tbody', null,
                        ...alerts.low_stock.map(function (a, i) {
                          return e('tr', { key: i, style: a.v_stocks <= 2 ? { background: '#fed7d7' } : null },
                            e('td', null, a.ref),
                            e('td', null, a.nom),
                            e('td', { style: { textAlign: 'right', fontWeight: 'bold', color: a.v_stocks <= 2 ? '#c53030' : '#dd6b20' } }, String(a.v_stocks))
                          );
                        })
                      )
                    )
                  )
                )
              : e('p', { className: 'notice success', style: { marginBottom: '16px' } }, '\u2705 Aucun article en stock faible.'),

            user.type === 'admin' && alerts.overdue_receivables && alerts.overdue_receivables.length > 0
              ? e(
                  'section',
                  { className: 'panel', style: { marginBottom: '16px' } },
                  e('div', { className: 'panel-heading' },
                    e('h2', null, '\uD83D\uDCB0 Cr\u00e9ances en retard (' + alerts.counts.overdue + ')')
                  ),
                  e(
                    'div',
                    { className: 'table-wrap' },
                    e(
                      'table',
                      null,
                      e('thead', null, e('tr', null,
                        e('th', null, 'N\u00b0 Facture'),
                        e('th', null, 'Client'),
                        e('th', null, '\u00c9ch\u00e9ance'),
                        e('th', { style: { textAlign: 'right' } }, 'Montant d\u00fb')
                      )),
                      e('tbody', null,
                        ...alerts.overdue_receivables.map(function (s, i) {
                          return e('tr', { key: i },
                            e('td', null, s.invoice_number),
                            e('td', null, s.customer_name),
                            e('td', null, s.due_date),
                            e('td', { style: { textAlign: 'right', fontWeight: 'bold', color: '#c53030' } },
                              s.amount + ' ' + (currency || 'TND'))
                          );
                        })
                      )
                    )
                  )
                )
              : user.type === 'admin'
                ? e('p', { className: 'notice success', style: { marginBottom: '16px' } }, '\u2705 Aucune cr\u00e9ance en retard.')
                : null,

            alerts.upcoming_fairs && alerts.upcoming_fairs.length > 0
              ? e(
                  'section',
                  { className: 'panel', style: { marginBottom: '16px' } },
                  e('div', { className: 'panel-heading' },
                    e('h2', null, '\uD83C\uDFAA Foires \u00e0 venir (' + alerts.counts.upcoming_fairs + ')')
                  ),
                  e(
                    'div',
                    { className: 'table-wrap' },
                    e(
                      'table',
                      null,
                      e('thead', null, e('tr', null,
                        e('th', null, 'Nom'),
                        e('th', null, 'Lieu'),
                        e('th', null, 'D\u00e9but'),
                        e('th', null, 'Fin')
                      )),
                      e('tbody', null,
                        ...alerts.upcoming_fairs.map(function (f, i) {
                          return e('tr', { key: i },
                            e('td', null, f.nom),
                            e('td', null, f.lieu || '\u2014'),
                            e('td', null, f.start_date),
                            e('td', null, f.end_date)
                          );
                        })
                      )
                    )
                  )
                )
              : e('p', { className: 'notice success', style: { marginBottom: '16px' } }, '\u2705 Aucune foire pr\u00e9vue dans les 7 prochains jours.'),

            user.type === 'admin' && alerts.unconfigured_products && alerts.unconfigured_products.length > 0
              ? e(
                  'section',
                  { className: 'panel', style: { marginBottom: '16px' } },
                  e('div', { className: 'panel-heading' },
                    e('h2', null, '\uD83D\uDD27 Produits non configur\u00e9s (' + alerts.counts.unconfigured + ')')
                  ),
                  e(
                    'div',
                    { className: 'table-wrap' },
                    e(
                      'table',
                      null,
                      e('thead', null, e('tr', null,
                        e('th', null, 'Code'),
                        e('th', null, 'D\u00e9signation')
                      )),
                      e('tbody', null,
                        ...alerts.unconfigured_products.map(function (p, i) {
                          return e('tr', { key: i },
                            e('td', null, p.product_code),
                            e('td', null, p.gen_name)
                          );
                        })
                      )
                    )
                  )
                )
              : null
          )
        : null
    )
  );
}

// ---------------------------------------------------------------------------
// Reusable UI Components: Pagination & Toast
// ---------------------------------------------------------------------------

function Pagination({ page, pages, total, onPageChange }) {
  if (!pages || pages <= 1) return null;
  return e(
    'div',
    {
      className: 'pagination-bar',
      style: {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 0',
        marginTop: '12px',
        borderTop: '1px solid #e2e8f0',
        fontSize: '13px',
        color: '#4a5568',
      },
    },
    e('span', null, 'Page ' + page + ' sur ' + pages + ' (' + total + ' \u00e9l\u00e9ment' + (total > 1 ? 's' : '') + ')'),
    e(
      'div',
      { style: { display: 'flex', gap: '6px' } },
      e(
        'button',
        {
          type: 'button',
          className: 'button secondary small-button',
          disabled: page <= 1,
          onClick: function () { onPageChange(1); },
          style: { padding: '4px 8px', fontSize: '12px' },
        },
        '\u00AB Premier'
      ),
      e(
        'button',
        {
          type: 'button',
          className: 'button secondary small-button',
          disabled: page <= 1,
          onClick: function () { onPageChange(page - 1); },
          style: { padding: '4px 8px', fontSize: '12px' },
        },
        '\u2039 Pr\u00e9c\u00e9dent'
      ),
      e(
        'button',
        {
          type: 'button',
          className: 'button secondary small-button',
          disabled: page >= pages,
          onClick: function () { onPageChange(page + 1); },
          style: { padding: '4px 8px', fontSize: '12px' },
        },
        'Suivant \u203A'
      ),
      e(
        'button',
        {
          type: 'button',
          className: 'button secondary small-button',
          disabled: page >= pages,
          onClick: function () { onPageChange(pages); },
          style: { padding: '4px 8px', fontSize: '12px' },
        },
        'Dernier \u00BB'
      )
    )
  );
}

function Toast({ message, type, onClose }) {
  useEffect(function () {
    if (!message) return;
    var timer = setTimeout(onClose, 4000);
    return function () { clearTimeout(timer); };
  }, [message]);

  if (!message) return null;
  var isError = type === 'error';
  return e(
    'div',
    {
      className: 'toast ' + (isError ? 'toast-error' : 'toast-success'),
      style: {
        position: 'fixed',
        top: '20px',
        right: '20px',
        zIndex: 9999,
        padding: '12px 20px',
        borderRadius: '8px',
        color: '#fff',
        backgroundColor: isError ? '#e53e3e' : '#38a169',
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        fontSize: '14px',
      },
    },
    e('span', null, isError ? '\u26A0\uFE0F' : '\u2705'),
    e('span', null, message),
    e(
      'button',
      {
        type: 'button',
        onClick: onClose,
        style: {
          background: 'none',
          border: 'none',
          color: '#fff',
          cursor: 'pointer',
          fontSize: '16px',
          padding: '0 4px',
          lineHeight: 1,
        },
      },
      '\u00D7'
    )
  );
}


function ClientsPage({ user, onBack, onArticles, onLogout }) {

  const canManage = hasViewPermission(user, 'client');
  const [clients, setClients] = useState([]);
  const [search, setSearch] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  useEffect(() => { setCurrentPage(1); }, [search]);
  const [form, setForm] = useState({
    id: '',
    nom: '',
    prenom: '',
    tel: '',
    email: '',
    specialite: '',
    ville: '',
  });
  const [editingId, setEditingId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function refreshClients() {
    const data = await api('/clients');
    setClients(data);
  }

  useEffect(() => {
    refreshClients()
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  function resetForm() {
    setEditingId(null);
    setForm({
      id: '',
      nom: '',
      prenom: '',
      tel: '',
      email: '',
      specialite: '',
      ville: '',
    });
  }

  function startEdit(client) {
    setEditingId(client.id);
    setForm({
      id: String(client.id),
      nom: client.nom,
      prenom: client.prenom,
      tel: client.tel,
      email: client.email,
      specialite: client.specialite || '',
      ville: client.ville || '',
    });
    setMessage('');
    setError('');
  }

  async function saveClient(event) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    setError('');
    const formData = new FormData(event.currentTarget);
    const payload = {
      nom: formData.get('nom'),
      prenom: formData.get('prenom'),
      tel: formData.get('tel'),
      email: formData.get('email'),
      specialite: formData.get('specialite'),
      ville: formData.get('ville'),
    };
    const id = formData.get('id');
    if (!editingId && id) {
      payload.id = Number(id);
    }

    try {
      const data = await api(editingId ? `/clients/${editingId}` : '/clients', {
        method: editingId ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      });
      setMessage(data.message);
      resetForm();
      await refreshClients();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function deleteClient(client) {
    if (!window.confirm(`Supprimer le client ${client.prenom} ${client.nom} ?`)) {
      return;
    }
    setMessage('');
    setError('');
    try {
      const data = await api(`/clients/${client.id}`, { method: 'DELETE' });
      setMessage(data.message);
      await refreshClients();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  const filteredClients = clients.filter((client) =>
    `${client.id} ${client.nom} ${client.prenom} ${client.tel} ${client.email} ${client.specialite || ''} ${client.ville || ''}`
      .toLowerCase()
      .includes(search.toLowerCase())
  );
  const perPage = parseInt(user && user.lpp ? user.lpp : 10, 10);
  const totalPages = Math.ceil(filteredClients.length / perPage) || 1;
  const paginatedClients = filteredClients.slice((currentPage - 1) * perPage, currentPage * perPage);

  return e(
    'main',
    { className: 'dashboard' },
    e(
      'header',
      { className: 'topbar' },
      e(
        'div',
        null,
        e('strong', null, 'OKBA INTER'),
        e('span', { className: 'topbar-label' }, 'Gestion des clients')
      ),
      e(
        'div',
        { className: 'topbar-user' },
        user.type === 'admin'
          ? e('button', { className: 'button secondary small-button', onClick: onBack }, 'Utilisateurs')
          : null,
        e('button', { className: 'button secondary small-button', onClick: onArticles }, 'Articles'),
        e('span', null, `${user.prenom} ${user.nom}`),
        e('button', { className: 'button secondary small-button', onClick: onLogout }, 'Déconnexion')
      )
    ),
    e(
      'div',
      { className: 'content' },
      e(
        'div',
        { className: 'page-heading' },
        e(
          'div',
          null,
          e('p', { className: 'eyebrow' }, 'GESTION COMMERCIALE'),
          e('h1', null, 'Clients'),
          e('p', { className: 'subtitle' }, 'Consultez et recherchez les fiches clients.')
        ),
        e('span', { className: 'count-badge' }, `${clients.length} client${clients.length === 1 ? '' : 's'}`),
        e('button', { className: 'button secondary small-button', onClick: function () { window.open(API_URL + '/clients/export', '_blank'); } }, '\uD83D\uDCE5 Exporter CSV')
      ),
      message ? e('p', { className: 'notice success', role: 'status' }, message) : null,
      error ? e('p', { className: 'notice error', role: 'alert' }, error) : null,
      e(
        'div',
        { className: 'admin-grid clients-grid' },
        e(
          'section',
          { className: 'panel' },
          e(
            'div',
            { className: 'panel-heading' },
            e('h2', null, 'Répertoire des clients'),
            e('span', null, loading ? 'Chargement...' : `${filteredClients.length} affiché(s)`)
          ),
          e('input', {
            className: 'search-input',
            type: 'search',
            placeholder: 'Rechercher par nom, téléphone ou e-mail...',
            value: search,
            onChange: (event) => setSearch(event.target.value),
            'aria-label': 'Rechercher un client',
          }),
          e(
            'div',
            { className: 'table-wrap' },
            e(
              'table',
              null,
              e(
                'thead',
                null,
                e('tr', null, e('th', null, 'ID'), e('th', null, 'Client'), e('th', null, 'Téléphone'), e('th', null, 'E-mail'), e('th', null, 'Spécialité'), e('th', null, 'Ville'), canManage ? e('th', null, 'Actions') : null)
              ),
              e(
                'tbody',
                null,
                filteredClients.length
                  ? paginatedClients.map((client) =>
                      e(
                        'tr',
                        { key: client.id },
                        e('td', null, client.id),
                        e('td', null, e('strong', null, `${client.prenom} ${client.nom}`)),
                        e('td', null, client.tel),
                        e('td', null, client.email),
                        e('td', null, client.specialite || '—'),
                        e('td', null, client.ville || '—'),
                        canManage
                          ? e(
                              'td',
                              { className: 'actions-cell' },
                              e('button', { className: 'text-button', onClick: () => startEdit(client) }, 'Modifier'),
                              e('button', { className: 'text-button danger-text', onClick: () => deleteClient(client) }, 'Supprimer')
                            )
                          : null
                      )
                    )
                  : e('tr', null, e('td', { className: 'empty-state', colSpan: canManage ? 7 : 6 }, loading ? 'Chargement des clients...' : 'Aucun client trouvé.'))
              ),
          e(Pagination, { page: currentPage, pages: totalPages, total: filteredClients.length, onPageChange: setCurrentPage })
            )
          )
        ),
        canManage
          ? e(
              'section',
              { className: 'panel form-panel' },
              e(
                'div',
                { className: 'panel-heading' },
                e('h2', null, editingId ? 'Modifier le client' : 'Ajouter un client'),
                editingId ? e('button', { className: 'text-button', onClick: resetForm }, 'Annuler') : null
              ),
              e(
                'form',
                { onSubmit: saveClient },
                e(
                  'div',
                  { className: 'form-row' },
                  e(
                    'label',
                    null,
                    'Prénom',
                    e('input', {
                      name: 'prenom',
                      value: form.prenom,
                      onChange: (event) => setForm({ ...form, prenom: event.target.value }),
                      required: true,
                    })
                  ),
                  e(
                    'label',
                    null,
                    'Nom',
                    e('input', {
                      name: 'nom',
                      value: form.nom,
                      onChange: (event) => setForm({ ...form, nom: event.target.value }),
                      required: true,
                    })
                  )
                ),
                e(
                  'label',
                  null,
                  'Téléphone',
                  e('input', {
                    name: 'tel',
                    type: 'tel',
                    value: form.tel,
                    onChange: (event) => setForm({ ...form, tel: event.target.value }),
                    required: true,
                  })
                ),
                e(
                  'label',
                  null,
                  'Adresse e-mail',
                  e('input', {
                    name: 'email',
                    type: 'email',
                    value: form.email,
                    onChange: (event) => setForm({ ...form, email: event.target.value }),
                    required: true,
                  })
                ),
                e(
                  'label',
                  null,
                  'Spécialité',
                  e('input', {
                    name: 'specialite',
                    value: form.specialite,
                    onChange: (event) => setForm({ ...form, specialite: event.target.value }),
                    maxLength: 100,
                  })
                ),
                e(
                  'label',
                  null,
                  'Ville',
                  e('input', {
                    name: 'ville',
                    value: form.ville,
                    onChange: (event) => setForm({ ...form, ville: event.target.value }),
                    maxLength: 100,
                  })
                ),
                !editingId
                  ? e(
                      'label',
                      null,
                      'Identifiant (facultatif)',
                      e('input', {
                        name: 'id',
                        type: 'number',
                        min: 1,
                        value: form.id,
                        onChange: (event) => setForm({ ...form, id: event.target.value }),
                        placeholder: 'Attribué automatiquement si vide',
                      })
                    )
                  : null,
                e(
                  'button',
                  { type: 'submit', className: 'button', disabled: saving },
                  saving ? 'Enregistrement...' : editingId ? 'Enregistrer les changements' : 'Créer le client'
                )
              )
            )
          : null
      )
    )
  );
}


// ---------------------------------------------------------------------------
// Barcode (Code-128) Generator & Printable Label Component
// ---------------------------------------------------------------------------

const CODE128_PATTERNS = [
  "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
  "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
  "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
  "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
  "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
  "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
  "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
  "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
  "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
  "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
  "114131", "311141", "411131", "211412", "211214", "211232", "2331112"
];

function encodeCode128(text) {
  const str = String(text || '').trim();
  if (!str) return [];
  let codes = [104];
  let checksum = 104;
  for (let i = 0; i < str.length; i++) {
    const val = str.charCodeAt(i) - 32;
    codes.push(val);
    checksum += val * (i + 1);
  }
  codes.push(checksum % 103);
  codes.push(106);
  let bars = [];
  let isBar = true;
  codes.forEach(c => {
    const pat = CODE128_PATTERNS[c] || CODE128_PATTERNS[0];
    for (let j = 0; j < pat.length; j++) {
      bars.push({ width: parseInt(pat[j], 10), isBar });
      isBar = !isBar;
    }
  });
  return bars;
}

function BarcodeSVG({ code, width = 180, height = 55, showText = true }) {
  if (!code) return null;
  const bars = encodeCode128(code);
  let totalWidth = bars.reduce((sum, b) => sum + b.width, 0);
  let currentX = 0;
  const rects = [];
  bars.forEach((b, i) => {
    if (b.isBar) {
      rects.push(
        e('rect', {
          key: i,
          x: currentX,
          y: 0,
          width: b.width,
          height: height - (showText ? 15 : 0),
          fill: '#000',
        })
      );
    }
    currentX += b.width;
  });

  return e(
    'svg',
    {
      viewBox: `0 0 ${totalWidth} ${height}`,
      style: { width: `${width}px`, height: `${height}px`, display: 'block', margin: '0 auto' },
    },
    rects,
    showText
      ? e(
          'text',
          {
            x: totalWidth / 2,
            y: height - 2,
            textAnchor: 'middle',
            fontSize: '11px',
            fontFamily: 'monospace',
            fontWeight: 'bold',
            fill: '#000',
          },
          code
        )
      : null
  );
}

function BarcodeModal({ item, onClose }) {
  if (!item) return null;
  const code = item.barcode || item.product_code || item.ref || 'SANS-CODE';
  const name = item.gen_name || item.nom || 'Article';
  const price = item.price ? `${item.price} TND` : '';

  function printLabel() {
    const printWindow = window.open('', '_blank', 'width=450,height=320');
    if (!printWindow) return;
    const svgEl = document.getElementById('printable-barcode-svg');
    const svgHtml = svgEl ? svgEl.outerHTML : '';
    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="utf-8">
        <title>Étiquette Code-Barres - ${name}</title>
        <style>
          @page { size: auto; margin: 4mm; }
          body { font-family: sans-serif; text-align: center; margin: 0; padding: 10px; background: #fff; }
          .label { border: 1px dashed #cbd5e1; padding: 12px; display: inline-block; border-radius: 6px; width: 240px; }
          h3 { margin: 2px 0 4px; font-size: 14px; text-transform: uppercase; color: #0f172a; }
          p { margin: 2px 0; font-size: 11px; color: #475569; }
          .price { font-size: 18px; font-weight: bold; color: #16a34a; margin-top: 6px; }
        </style>
      </head>
      <body>
        <div class="label">
          <p style="font-size: 10px; color: #94a3b8; margin: 0 0 2px; font-weight: bold; letter-spacing: 1px;">OKBA INTER</p>
          <h3>${name}</h3>
          <p>Réf: ${item.ref || item.product_code || code}</p>
          <div style="margin: 8px auto;">${svgHtml}</div>
          ${price ? `<div class="price">${price}</div>` : ''}
        </div>
        <script>
          window.onload = function() { window.print(); window.close(); };
        </script>
      </body>
      </html>
    `);
    printWindow.document.close();
  }

  return e(
    'div',
    {
      style: {
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 99999,
      },
      onClick: (evt) => { if (evt.target === evt.currentTarget) onClose(); },
    },
    e(
      'div',
      {
        style: {
          background: '#fff', borderRadius: '10px', padding: '24px', maxWidth: '380px', width: '90%',
          textAlign: 'center', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)',
        },
      },
      e('p', { style: { margin: 0, fontSize: '11px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: 600 } }, 'OKBA INTER — ÉTIQUETTE ARTICLE'),
      e('h3', { style: { margin: '8px 0 2px', fontSize: '18px', color: '#0f172a' } }, name),
      e('p', { style: { margin: '0 0 14px', color: '#64748b', fontSize: '12px' } }, `Code : ${code}`),
      e('div', { id: 'printable-barcode-svg', style: { padding: '12px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0', margin: '0 auto 16px' } },
        e(BarcodeSVG, { code, width: 220, height: 75, showText: true })
      ),
      price ? e('p', { style: { fontSize: '22px', fontWeight: 'bold', color: '#16a34a', margin: '0 0 16px' } }, price) : null,
      e(
        'div',
        { style: { display: 'flex', gap: '8px', justifyContent: 'center' } },
        e('button', { className: 'button', onClick: printLabel }, '🖨️ Imprimer étiquette'),
        e('button', { className: 'button secondary', onClick: onClose }, 'Fermer')
      )
    )
  );
}


const EMPTY_ARTICLE = {
  ref: '',
  famille: '',
  description: '',
  categorie: '',
  nom: '',
  barcode: '',
  v_entrees: '0',
  v_retour: '0',
};

function ArticlesPage({ user, onBack, onClients, onStock, onLogout }) {
  const canManage = hasViewPermission(user, 'article');
  const [articles, setArticles] = useState([]);
  const [search, setSearch] = useState('');
  const [form, setForm] = useState(EMPTY_ARTICLE);
  const [editingRef, setEditingRef] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [barcodeModalItem, setBarcodeModalItem] = useState(null);

  async function refreshArticles() {
    const data = await api('/articles');
    setArticles(data);
  }

  useEffect(() => {
    refreshArticles()
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  function resetForm() {
    setEditingRef(null);
    setForm(EMPTY_ARTICLE);
  }

  function startEdit(article) {
    setEditingRef(article.ref);
    setForm({
      ref: article.ref,
      famille: article.famille,
      description: article.description,
      categorie: article.categorie,
      nom: article.nom,
      barcode: article.barcode || '',
      v_entrees: String(article.v_entrees),
      v_retour: String(article.v_retour),
    });
    setMessage('');
    setError('');
  }

  async function saveArticle(event) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    setError('');
    const formData = new FormData(event.currentTarget);
    const payload = {
      ref: formData.get('ref'),
      famille: formData.get('famille'),
      description: formData.get('description'),
      categorie: formData.get('categorie'),
      nom: formData.get('nom'),
      barcode: (formData.get('barcode') || '').trim(),
      v_entrees: Number(formData.get('v_entrees')),
      v_retour: Number(formData.get('v_retour')),
    };

    try {
      const path = editingRef
        ? `/articles/${encodeURIComponent(editingRef)}`
        : '/articles';
      const data = await api(path, {
        method: editingRef ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      });
      setMessage(data.message);
      resetForm();
      await refreshArticles();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function deleteArticle(article) {
    if (!window.confirm(`Supprimer l’article ${article.nom} (${article.ref}) ?`)) {
      return;
    }
    setMessage('');
    setError('');
    try {
      const data = await api(`/articles/${encodeURIComponent(article.ref)}`, {
        method: 'DELETE',
      });
      setMessage(data.message);
      await refreshArticles();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  const filteredArticles = articles.filter((article) =>
    `${article.ref} ${article.nom} ${article.famille} ${article.description} ${article.categorie}`
      .toLowerCase()
      .includes(search.toLowerCase())
  );
  const perPage = parseInt(user && user.lpp ? user.lpp : 10, 10);
  const totalPages = Math.ceil(filteredArticles.length / perPage) || 1;
  const paginatedArticles = filteredArticles.slice((currentPage - 1) * perPage, currentPage * perPage);

  return e(
    'main',
    { className: 'dashboard' },
    e(
      'header',
      { className: 'topbar' },
      e(
        'div',
        null,
        e('strong', null, 'OKBA INTER'),
        e('span', { className: 'topbar-label' }, 'Articles et stock')
      ),
      e(
        'div',
        { className: 'topbar-user' },
        user.type === 'admin'
          ? e('button', { className: 'button secondary small-button', onClick: onBack }, 'Utilisateurs')
          : null,
        e('button', { className: 'button secondary small-button', onClick: onClients }, 'Clients'),
        e('button', { className: 'button secondary small-button', onClick: onStock }, 'Stock'),
        e('span', null, `${user.prenom} ${user.nom}`),
        e('button', { className: 'button secondary small-button', onClick: onLogout }, 'Déconnexion')
      )
    ),
    e(
      'div',
      { className: 'content' },
      e(
        'div',
        { className: 'page-heading' },
        e(
          'div',
          null,
          e('p', { className: 'eyebrow' }, 'GESTION COMMERCIALE'),
          e('h1', null, 'Articles et stock'),
          e('p', { className: 'subtitle' }, 'Consultez le catalogue et les quantités disponibles.')
        ),
        e('span', { className: 'count-badge' }, `${articles.length} article${articles.length === 1 ? '' : 's'}`),
        e('button', { className: 'button secondary small-button', onClick: function () { window.open(API_URL + '/articles/export', '_blank'); } }, '\uD83D\uDCE5 Exporter CSV')
      ),
      message ? e('p', { className: 'notice success', role: 'status' }, message) : null,
      error ? e('p', { className: 'notice error', role: 'alert' }, error) : null,
      e(
        'div',
        { className: 'admin-grid clients-grid' },
        e(
          'section',
          { className: 'panel' },
          e(
            'div',
            { className: 'panel-heading' },
            e('h2', null, 'Catalogue'),
            e('span', null, loading ? 'Chargement...' : `${filteredArticles.length} affiché(s)`)
          ),
          e('input', {
            className: 'search-input',
            type: 'search',
            placeholder: 'Rechercher par référence, nom, famille...',
            value: search,
            onChange: (event) => setSearch(event.target.value),
            'aria-label': 'Rechercher un article',
          }),
          e(
            'div',
            { className: 'table-wrap' },
            e(
              'table',
              null,
              e(
                'thead',
                null,
                e(
                  'tr',
                  null,
                  e('th', null, 'Référence'),
                  e('th', null, 'Article'),
                  e('th', null, 'Famille / catégorie'),
                  e('th', null, 'Entrées'),
                  e('th', null, 'Retours'),
                  e('th', null, 'Stock'),
                  canManage ? e('th', null, 'Actions') : null
                )
              ),
              e(
                'tbody',
                null,
                filteredArticles.length
                  ? paginatedArticles.map((article) =>
                      e(
                        'tr',
                        { key: article.ref },
                        e('td', null, e('strong', null, article.ref)),
                        e(
                          'td',
                          null,
                          e('strong', null, article.nom),
                          e('span', { className: 'cell-detail' }, article.description)
                        ),
                        e(
                          'td',
                          null,
                          article.famille,
                          e('span', { className: 'cell-detail' }, article.categorie)
                        ),
                        e('td', null, article.v_entrees),
                        e('td', null, article.v_retour),
                        e(
                          'td',
                          null,
                          e(
                            'span',
                            {
                              className: `stock-badge${article.v_stocks < 10 ? ' low-stock' : ''}`,
                            },
                            article.v_stocks
                          )
                        ),
                        canManage
                          ? e(
                              'td',
                              { className: 'actions-cell' },
                              e('button', { className: 'text-button', onClick: () => startEdit(article) }, 'Modifier'),
                              e('button', { className: 'text-button danger-text', onClick: () => deleteArticle(article) }, 'Supprimer')
                            )
                          : null
                      )
                    )
                  : e(
                      'tr',
                      null,
                      e(
                        'td',
                        { className: 'empty-state', colSpan: canManage ? 7 : 6 },
                        loading ? 'Chargement des articles...' : 'Aucun article trouvé.'
                      ),
          e(Pagination, { page: currentPage, pages: totalPages, total: filteredArticles.length, onPageChange: setCurrentPage })
                    )
              )
            )
          )
        ),
        canManage
          ? e(
              'section',
              { className: 'panel form-panel' },
              e(
                'div',
                { className: 'panel-heading' },
                e('h2', null, editingRef ? 'Modifier l’article' : 'Ajouter un article'),
                editingRef ? e('button', { className: 'text-button', onClick: resetForm }, 'Annuler') : null
              ),
              e(
                'form',
                { onSubmit: saveArticle },
                e(
                  'div',
                  { className: 'form-row' },
                  e(
                    'label',
                    null,
                    'Référence',
                    e('input', {
                      name: 'ref',
                      value: form.ref,
                      onChange: (event) => setForm({ ...form, ref: event.target.value }),
                      maxLength: 50,
                      required: true,
                    })
                  ),
                  e(
                    'label',
                    null,
                    'Nom',
                    e('input', {
                      name: 'nom',
                      value: form.nom,
                      onChange: (event) => setForm({ ...form, nom: event.target.value }),
                      maxLength: 160,
                      required: true,
                    })
                  )
                ),
                e(
                  'label',
                  null,
                  'Description',
                  e('input', {
                    name: 'description',
                    value: form.description,
                    onChange: (event) => setForm({ ...form, description: event.target.value }),
                    maxLength: 255,
                    required: true,
                  })
                ),
                e(
                  'div',
                  { className: 'form-row' },
                  e(
                    'label',
                    null,
                    'Famille',
                    e('input', {
                      name: 'famille',
                      value: form.famille,
                      onChange: (event) => setForm({ ...form, famille: event.target.value }),
                      maxLength: 120,
                    })
                  ),
                  e(
                    'label',
                    null,
                    'Catégorie',
                    e('input', {
                      name: 'categorie',
                      value: form.categorie,
                      onChange: (event) => setForm({ ...form, categorie: event.target.value }),
                      maxLength: 120,
                    })
                  )
                ),
                e(
                  'div',
                  { className: 'form-row' },
                  e(
                    'label',
                    null,
                    'Quantité entrée',
                    e('input', {
                      name: 'v_entrees',
                      type: 'number',
                      min: 0,
                      value: form.v_entrees,
                      onChange: (event) => setForm({ ...form, v_entrees: event.target.value }),
                      required: true,
                    })
                  ),
                  e(
                    'label',
                    null,
                    'Quantité retournée',
                    e('input', {
                      name: 'v_retour',
                      type: 'number',
                      min: 0,
                      value: form.v_retour,
                      onChange: (event) => setForm({ ...form, v_retour: event.target.value }),
                      required: true,
                    })
                  )
                ),
                e('p', { className: 'stock-help' }, 'Le stock disponible est calculé automatiquement : entrées − retours.'),
                e(
                  'button',
                  { type: 'submit', className: 'button', disabled: saving },
                  saving ? 'Enregistrement...' : editingRef ? 'Enregistrer les changements' : 'Créer l’article'
                )
              )
            )
          : null
      )
    )
  );
}

const EMPTY_POS_PRODUCT = {
  article_ref: '',
  product_code: '',
  gen_name: '',
  product_name: '',
  supplier: '',
  barcode: '',
  date_arrival: '',
  expiry_date: '',
  price: '',
  o_price: '',
  pricing_configured: false,
  qty: '0',
};

function POSPage({ user, currency, onBack, onLogout }) {
  const isAdmin = user.type === 'admin';
  const [tab, setTab] = useState('sale');
  const [fairContexts, setFairContexts] = useState([]);
  const [selectedFairId, setSelectedFairId] = useState('');
  const [selectedSellerId, setSelectedSellerId] = useState('');
  const [products, setProducts] = useState([]);
  const [linkedArticles, setLinkedArticles] = useState([]);
  const [sales, setSales] = useState([]);
  const [purchases, setPurchases] = useState([]);
  const [receivables, setReceivables] = useState([]);
  const [collections, setCollections] = useState([]);
  const [barcodeInput, setBarcodeInput] = useState('');
  const [barcodeToast, setBarcodeToast] = useState('');
  const [barcodeModalItem, setBarcodeModalItem] = useState(null);
  const barcodeInputRef = useRef(null);
  const [collectionSummary, setCollectionSummary] = useState(null);
  const [purchaseItems, setPurchaseItems] = useState([]);
  const [purchaseForm, setPurchaseForm] = useState({
    invoice_number: '',
    date: new Date().toISOString().slice(0, 10),
    supplier: '',
    remarks: '',
  });
  const [purchaseDraft, setPurchaseDraft] = useState({
    product_id: '',
    qty: '1',
    unit_cost: '',
  });
  const [selectedPurchase, setSelectedPurchase] = useState(null);
  const [salesReport, setSalesReport] = useState(null);
  const [fairReport, setFairReport] = useState(null);
  const [reportFairId, setReportFairId] = useState('');
  const [reportSellerId, setReportSellerId] = useState('');
  const [cart, setCart] = useState({});
  const [productSearch, setProductSearch] = useState('');
  const [saleSearch, setSaleSearch] = useState('');
  const [dateRange, setDateRange] = useState({ from: '', to: '' });
  const [paymentType, setPaymentType] = useState('cash');
  const [cashReceived, setCashReceived] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [customerName, setCustomerName] = useState('');
  const [selectedSale, setSelectedSale] = useState(null);
  const [paymentAmount, setPaymentAmount] = useState('');
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().slice(0, 10));
  const [paymentRemarks, setPaymentRemarks] = useState('');
  const [productForm, setProductForm] = useState(EMPTY_POS_PRODUCT);
  function playBeep(success = true) {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      if (success) {
        osc.frequency.setValueAtTime(880, ctx.currentTime);
        gain.gain.setValueAtTime(0.15, ctx.currentTime);
        osc.start();
        osc.stop(ctx.currentTime + 0.12);
      } else {
        osc.frequency.setValueAtTime(220, ctx.currentTime);
        gain.gain.setValueAtTime(0.2, ctx.currentTime);
        osc.start();
        osc.stop(ctx.currentTime + 0.25);
      }
    } catch (e) {}
  }

  function handleBarcodeScan(forcedCode) {
    const raw = (forcedCode || barcodeInput || '').trim();
    if (!raw) return;
    setBarcodeInput('');

    const matched = products.find(
      (p) =>
        (p.barcode && p.barcode.trim().toLowerCase() === raw.toLowerCase()) ||
        (p.product_code && p.product_code.trim().toLowerCase() === raw.toLowerCase()) ||
        (p.article_ref && p.article_ref.trim().toLowerCase() === raw.toLowerCase())
    );

    if (!matched) {
      playBeep(false);
      setError(`Code-barres inconnu : « ${raw} ». Aucun article correspondant.`);
      setBarcodeToast(`❌ Code « ${raw} » introuvable`);
      setTimeout(() => setBarcodeToast(''), 3500);
      if (barcodeInputRef.current) barcodeInputRef.current.focus();
      return;
    }

    const available = availableQuantity(matched);
    const currentQty = cart[matched.product_id] || 0;
    if (currentQty >= available) {
      playBeep(false);
      setError(`Stock insuffisant pour « ${matched.gen_name} » (disponible : ${available}).`);
      setBarcodeToast(`⚠️ Stock épuisé : ${matched.gen_name}`);
      setTimeout(() => setBarcodeToast(''), 3500);
      if (barcodeInputRef.current) barcodeInputRef.current.focus();
      return;
    }

    addToCart(matched);
    playBeep(true);
    setError('');
    const nextQty = currentQty + 1;
    setBarcodeToast(`✓ ${matched.gen_name} (${nextQty}x — ${(matched.price * nextQty).toFixed(2)} ${currency || 'TND'})`);
    setTimeout(() => setBarcodeToast(''), 3500);
    if (barcodeInputRef.current) barcodeInputRef.current.focus();
  }

  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === 'F2') {
        event.preventDefault();
        if (barcodeInputRef.current) barcodeInputRef.current.focus();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const [editingProductId, setEditingProductId] = useState(null);
  const [loading, setLoading] = useState(true);
const [saving, setSaving] = useState(false);

  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === 'F2') {
        event.preventDefault();
        const input = document.getElementById('pos-product-search');
        if (input) input.focus();
      } else if (event.key === 'Escape') {
        setSelectedSale(null);
        setSelectedPurchase(null);
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function refreshProducts() {
    setProducts(await api('/pos/products'));
  }

  async function refreshSales(filters = dateRange) {
    const params = new URLSearchParams();
    if (filters.from) params.set('from', filters.from);
    if (filters.to) params.set('to', filters.to);
    const suffix = params.size ? `?${params.toString()}` : '';
    setSales(await api(`/pos/sales${suffix}`));
  }

  async function refreshPurchases() {
    setPurchases(await api('/pos/purchases'));
  }

  async function refreshReceivables(filters = dateRange) {
    const params = new URLSearchParams();
    if (filters.from) params.set('from', filters.from);
    if (filters.to) params.set('to', filters.to);
    const suffix = params.size ? `?${params.toString()}` : '';
    const result = await api(`/pos/receivables${suffix}`);
    setReceivables(result.receivables);
  }

  async function refreshCollections(filters = dateRange) {
    const params = new URLSearchParams();
    if (filters.from) params.set('from', filters.from);
    if (filters.to) params.set('to', filters.to);
    const suffix = params.size ? `?${params.toString()}` : '';
    const result = await api(`/pos/collections${suffix}`);
    setCollections(result.collections);
    setCollectionSummary(result);
  }

  async function refreshSalesReport(filters = dateRange) {
    const params = new URLSearchParams();
    if (filters.from) params.set('from', filters.from);
    if (filters.to) params.set('to', filters.to);
    if (reportFairId) params.set('fair_id', reportFairId);
    if (reportSellerId) params.set('seller_id', reportSellerId);
    const suffix = params.size ? `?${params.toString()}` : '';
    setSalesReport(await api(`/pos/reports/sales${suffix}`));
  }

  async function refreshFairReport(filters = dateRange) {
    const params = new URLSearchParams();
    if (filters.from) params.set('from', filters.from);
    if (filters.to) params.set('to', filters.to);
    const suffix = params.size ? `?${params.toString()}` : '';
    setFairReport(await api(`/pos/reports/fairs${suffix}`));
  }

  useEffect(() => {
    Promise.all([
      refreshProducts(),
      refreshSales({ from: '', to: '' }),
      api('/pos/fair-contexts').then((contexts) => {
        setFairContexts(contexts);
        if (user.type === 'vendeur' && contexts.length === 1) {
          setSelectedFairId(String(contexts[0].fair_id));
          setSelectedSellerId(String(user.id));
        }
      }),
    ])
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  const selectedFairContext = fairContexts.find(
    (context) => String(context.fair_id) === selectedFairId
  );
  const selectedReportFairContext = fairContexts.find(
    (context) => String(context.fair_id) === reportFairId
  );
  const fairInventory = Object.fromEntries(
    (selectedFairContext?.inventory || []).map((balance) => [
      balance.article_ref,
      balance.quantity,
    ])
  );
  const availableQuantity = (product) =>
    selectedFairContext
      ? (product.article_ref ? fairInventory[product.article_ref] || 0 : 0)
      : 0;

  const cartLines = products
    .filter((product) => cart[product.product_id])
    .map((product) => ({
      product,
      qty: cart[product.product_id],
      amount: product.price * cart[product.product_id],
    }));
  const total = cartLines.reduce((sum, line) => sum + line.amount, 0);
  const change = cashReceived === '' ? null : Number(cashReceived) - total;
  const filteredProducts = products.filter((product) =>
    availableQuantity(product) > 0 &&
    `${product.product_code} ${product.gen_name} ${product.product_name} ${product.supplier}`
      .toLowerCase()
      .includes(productSearch.toLowerCase())
  );
  const saleProducts = filteredProducts.filter((product) => product.pricing_configured);
  const filteredSales = sales.filter((sale) =>
    `${sale.invoice_number} ${sale.customer_name} ${sale.cashier} ${sale.fair_name} ${sale.seller_name} ${sale.type}`
      .toLowerCase()
      .includes(saleSearch.toLowerCase())
  );

  function addToCart(product) {
    setError('');
    setMessage('');
    const currentQuantity = cart[product.product_id] || 0;
    const available = availableQuantity(product);
    if (currentQuantity >= available) {
      setError(`Stock insuffisant pour « ${product.gen_name} » (disponible : ${available}).`);
      return;
    }
    setCart((current) => ({
      ...current,
      [product.product_id]: (current[product.product_id] || 0) + 1,
    }));
  }

  function updateCartQuantity(product, rawQuantity) {
    const quantity = Number(rawQuantity);
    if (!Number.isInteger(quantity) || quantity <= 0) {
      setCart((current) => {
        const next = { ...current };
        delete next[product.product_id];
        return next;
      });
      return;
    }
    const available = availableQuantity(product);
    if (quantity > available) {
      setError(`Stock disponible pour « ${product.gen_name} » : ${available}.`);
      return;
    }
    setError('');
    setCart((current) => ({ ...current, [product.product_id]: quantity }));
  }

  async function checkout(event) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    setError('');
    try {
      const response = await api('/pos/checkout', {
        method: 'POST',
        body: JSON.stringify({
          items: cartLines.map(({ product, qty }) => ({
            product_id: product.product_id,
            qty,
          })),
          payment_type: paymentType,
          customer_name: customerName,
          ...(selectedFairId
            ? {
                fair_id: Number(selectedFairId),
                seller_id: Number(selectedSellerId),
              }
            : {}),
          ...(paymentType === 'cash'
            ? { cash_received: Number(cashReceived) }
            : { due_date: dueDate }),
        }),
      });
      setSelectedSale(response.sale);
      setMessage(response.message);
      setCart({});
      setCustomerName('');
      setCashReceived('');
      setDueDate('');
      await Promise.all([refreshProducts(), refreshSales()]);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  function startEditProduct(product) {
    setEditingProductId(product.product_id);
    setProductForm({
      article_ref: product.article_ref || '',
      product_code: product.product_code,
      gen_name: product.gen_name,
      product_name: product.product_name,
      supplier: product.supplier,
      barcode: product.barcode || '',
      date_arrival: product.date_arrival,
      expiry_date: product.expiry_date,
      price: String(product.price),
      o_price: String(product.o_price),
      pricing_configured: product.pricing_configured,
      qty: String(product.qty),
    });
    setMessage('');
    setError('');
  }

  function resetProductForm() {
    setEditingProductId(null);
    setProductForm(EMPTY_POS_PRODUCT);
  }

  async function saveProduct(event) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    setError('');
    const payload = {
      ...productForm,
      price: Number(productForm.price),
      o_price: Number(productForm.o_price),
      pricing_configured: Boolean(productForm.pricing_configured),
      qty: Number(productForm.qty),
    };
    try {
      const path = editingProductId
        ? `/pos/products/${editingProductId}`
        : '/pos/products';
      const response = await api(path, {
        method: editingProductId ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      });
      setMessage(response.message);
      resetProductForm();
      await refreshProducts();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function importArticleProducts() {
    if (!window.confirm(
      'Créer un produit POS lié à chaque article non associé ? Les stocks actuels seront repris sans modification. Les prix de revient et de vente resteront à 0 et devront être configurés avant toute vente.'
    )) return;
    setSaving(true);
    setMessage('');
    setError('');
    try {
      const response = await api('/pos/products/import-articles', {
        method: 'POST',
        body: JSON.stringify({}),
      });
      setMessage(response.message);
      await refreshProducts();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function deleteProduct(product) {
    if (!window.confirm(`Supprimer le produit « ${product.gen_name} » ?`)) return;
    setMessage('');
    setError('');
    try {
      const response = await api(`/pos/products/${product.product_id}`, {
        method: 'DELETE',
      });
      setMessage(response.message);
      await refreshProducts();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function showSale(sale) {
    setError('');
    try {
      setSelectedSale(await api(`/pos/sales/${sale.transaction_id}`));
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function collectPayment(event) {
    event.preventDefault();
    if (!selectedSale) return;
    setSaving(true);
    setMessage('');
    setError('');
    try {
      const response = await api(`/pos/sales/${selectedSale.transaction_id}/collections`, {
        method: 'POST',
        body: JSON.stringify({
          amount: Number(paymentAmount),
          date: paymentDate,
          remarks: paymentRemarks,
        }),
      });
      setMessage(response.message);
      setPaymentAmount('');
      setPaymentRemarks('');
      const [saleDetails] = await Promise.all([
        api(`/pos/sales/${selectedSale.transaction_id}`),
        refreshReceivables(),
        refreshCollections(),
        refreshSales(),
      ]);
      setSelectedSale(saleDetails);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function searchReceivables(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      await refreshReceivables();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function searchCollections(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      await refreshCollections();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function searchSales(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      await refreshSales();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  function addPurchaseLine(event) {
    event.preventDefault();
    const productId = Number(purchaseDraft.product_id);
    const quantity = Number(purchaseDraft.qty);
    const unitCost = Number(purchaseDraft.unit_cost);
    const product = products.find((item) => item.product_id === productId);
    if (!product || !Number.isInteger(quantity) || quantity < 1 || purchaseDraft.unit_cost === '' || !Number.isFinite(unitCost) || unitCost < 0) {
      setError('Vérifiez le produit, la quantité et le coût unitaire.');
      return;
    }
    if (purchaseItems.some((item) => item.product_id === productId)) {
      setError('Ce produit est déjà dans le bon d’achat.');
      return;
    }
    setError('');
    setPurchaseItems((current) => [
      ...current,
      {
        product_id: productId,
        product_code: product.product_code,
        gen_name: product.gen_name,
        qty: quantity,
        unit_cost: unitCost,
      },
    ]);
    setPurchaseDraft({ product_id: '', qty: '1', unit_cost: '' });
  }

  async function savePurchase(event) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    setError('');
    try {
      const response = await api('/pos/purchases', {
        method: 'POST',
        body: JSON.stringify({ ...purchaseForm, items: purchaseItems }),
      });
      setMessage(response.message);
      setSelectedPurchase(response.purchase);
      setPurchaseItems([]);
      setPurchaseForm({
        invoice_number: '',
        date: new Date().toISOString().slice(0, 10),
        supplier: '',
        remarks: '',
      });
      await Promise.all([refreshProducts(), refreshPurchases()]);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function showPurchase(purchase) {
    setError('');
    try {
      setSelectedPurchase(
        await api(`/pos/purchases/${purchase.purchase_id}`)
      );
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function searchSalesReport(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      await refreshSalesReport();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function searchFairReport(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      await refreshFairReport();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  function money(value) {
    return new Intl.NumberFormat('fr-FR', {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Number(value || 0));
  }

  return e(
    'main',
    { className: 'dashboard' },
    e(
      'header',
      { className: 'topbar' },
      e(
        'div',
        null,
        e('strong', null, 'OKBA INTER'),
        e('span', { className: 'topbar-label' }, 'Caisse / Point de vente')
      ),
      e(
        'div',
        { className: 'topbar-user' },
        e('span', null, `${user.prenom} ${user.nom}`),
        e('button', { className: 'button secondary small-button', onClick: onBack }, 'Accueil'),
        e('button', { className: 'button secondary small-button', onClick: onLogout }, 'Déconnexion')
      )
    ),
    e(
      'div',
      { className: 'content' },
      e(
        'div',
        { className: 'page-heading' },
        e(
          'div',
          null,
          e('p', { className: 'eyebrow' }, 'VENTES ET INVENTAIRE'),
          e('h1', null, 'Caisse'),
          e('p', { className: 'subtitle' }, 'Enregistrez les ventes, consultez les reçus et suivez les produits.')
        ),
        e('span', { className: 'count-badge' }, `${products.length} produit${products.length === 1 ? '' : 's'}`)
      ),
      e(
        'div',
        { className: 'pos-tabs', role: 'tablist', 'aria-label': 'Modules de caisse' },
        ...[
          ['sale', 'Nouvelle vente'],
          ['history', 'Historique des ventes'],
          ...(isAdmin ? [
            ['products', 'Produits'],
            ['purchases', 'Achats'],
            ['report', 'Rapport ventes'],
            ['fair-report', 'Rapport des foires'],
          ] : []),
          ['receivables', 'Crédits clients'],
          ['collections', 'Encaissements'],
        ].map(([value, label]) =>
          e(
            'button',
            {
              key: value,
              type: 'button',
              role: 'tab',
              'aria-selected': tab === value,
              className: `button ${tab === value ? '' : 'secondary'}`,
              onClick: () => {
                setTab(value);
                setError('');
                setMessage('');
                setSelectedSale(null);
                setSelectedPurchase(null);
                if (value === 'purchases') {
                  refreshPurchases().catch((requestError) => setError(requestError.message));
                } else if (value === 'report') {
                  refreshSalesReport().catch((requestError) => setError(requestError.message));
                } else if (value === 'fair-report') {
                  refreshFairReport().catch((requestError) => setError(requestError.message));
                } else if (value === 'receivables') {
                  Promise.all([refreshReceivables(), refreshSales()])
                    .catch((requestError) => setError(requestError.message));
                } else if (value === 'collections') {
                  refreshCollections().catch((requestError) => setError(requestError.message));
                } else if (value === 'products' && isAdmin) {
                  api('/articles')
                    .then(setLinkedArticles)
                    .catch((requestError) => setError(requestError.message));
                }
              },
            },
            label
          )
        )
      ),
      message ? e('p', { className: 'notice success', role: 'status' }, message) : null,
      error ? e('p', { className: 'notice error', role: 'alert' }, error) : null,
      tab === 'sale'
        ? e(
            React.Fragment,
            null,
            selectedSale
              ? e(
                  'section',
                  { className: 'panel pos-receipt' },
                  e(
                    'div',
                    { className: 'panel-heading' },
                    e('h2', null, 'Reçu de vente'),
                    e(
                      'button',
                      { className: 'button secondary small-button no-print', onClick: () => window.print() },
                      'Imprimer'
                    ),
                    e(
                      'button',
                      { className: 'button secondary small-button no-print', onClick: function () { window.open(API_URL + '/pos/sales/' + selectedSale.transaction_id + '/receipt', '_blank'); } },
                      'Re\u00e7u imprimable'
                    )
                  ),
                  e('p', null, `Facture : ${selectedSale.invoice_number}`),
                  e('p', null, `Date : ${selectedSale.date} · Caissier : ${selectedSale.cashier}`),
                  selectedSale.fair_name
                    ? e('p', null, `Foire : ${selectedSale.fair_name} · Vendeur : ${selectedSale.seller_name} · Opérateur : ${selectedSale.cashier_user_name || selectedSale.cashier}`)
                    : null,
                  e('p', null, `Client : ${selectedSale.customer_name}`),
                  e(
                    'div',
                    { className: 'table-wrap' },
                    e(
                      'table',
                      null,
                      e('thead', null, e('tr', null,
                        e('th', null, 'Produit'),
                        e('th', null, 'Qté'),
                        e('th', null, 'Prix'),
                        e('th', null, 'Montant')
                      )),
                      e(
                        'tbody',
                        null,
                        ...(selectedSale.items || []).map((item) =>
                          e('tr', { key: item.transaction_id },
                            e('td', null, `${item.product_code} — ${item.gen_name}`),
                            e('td', null, item.qty),
                            e('td', null, money(item.price)),
                            e('td', null, money(item.amount))
                          )
                        )
                      )
                    )
                  ),
                  e('h2', { className: 'pos-total' }, `Total : ${money(selectedSale.amount)}`),
                  e('p', null, selectedSale.type === 'cash'
                    ? `Payé : ${money(selectedSale.cash_received)} · Monnaie : ${money(selectedSale.change)}`
                    : `À crédit · Échéance : ${selectedSale.due_date}`)
                )
              : null,
            e(
              'div',
              { className: 'pos-layout' },
              e(
                'section',
                { className: 'panel' },
                e(
                  'div',
                  { className: 'panel-heading' },
                  e('h2', null, 'Produits disponibles'),
                  e('span', null, loading ? 'Chargement...' : `${filteredProducts.length} produit(s)`)
                ),
                e('input', {
                  className: 'search-input',
                  type: 'search',
                  placeholder: 'Rechercher par code, nom ou fournisseur...',
                  value: productSearch,
                  onChange: (event) => setProductSearch(event.target.value),
                  'aria-label': 'Rechercher un produit',
                }),
                e(
                  'div',
                  { className: 'table-wrap' },
                  e(
                    'table',
                    null,
                    e('thead', null, e('tr', null,
                      e('th', null, 'Code / Barres'),
                      e('th', null, 'Produit'),
                      e('th', null, 'Stock'),
                      e('th', null, 'Prix'),
                      e('th', null, 'Ajouter')
                    )),
                    e(
                      'tbody',
                      null,
                      saleProducts.length
                        ? saleProducts.map((product) =>
                            e('tr', { key: product.product_id },
                              e('td', null,
                                e('div', { style: { display: 'flex', alignItems: 'center', gap: '4px' } },
                                  e('strong', null, product.product_code),
                                  e('button', {
                                    className: 'button secondary small-button',
                                    style: { padding: '1px 5px', fontSize: '11px' },
                                    onClick: () => setBarcodeModalItem(product),
                                    title: 'Voir étiquette code-barres'
                                  }, '🏷️')
                                ),
                                product.barcode
                                  ? e('div', { style: { fontFamily: 'monospace', fontSize: '11px', color: '#475569' } }, product.barcode)
                                  : null,
                                product.article_ref
                                  ? e('small', { className: 'stock-help' }, `Article lié : ${product.article_ref}`)
                                  : null
                              ),
                              e('td', null, `${product.gen_name}${product.product_name ? ` — ${product.product_name}` : ''}`),
                              e('td', null, availableQuantity(product)),
                              e('td', null, money(product.price)),
                              e('td', null, e('button', {
                                className: 'text-button',
                                disabled: availableQuantity(product) < 1 || (cart[product.product_id] || 0) >= availableQuantity(product),
                                onClick: () => addToCart(product),
                              }, 'Ajouter'))
                            )
                          )
                        : e('tr', null, e('td', { className: 'empty-state', colSpan: 5 },
                            loading ? 'Chargement des produits...' : 'Aucun produit. Les administrateurs peuvent en ajouter dans l’onglet Produits.'))
                    )
                  )
                )
              ),
              e(
                'section',
                { className: 'panel form-panel pos-cart' },
                e(
                  'div',
                  { className: 'panel-heading' },
                  e('h2', null, 'Panier'),
                  e('span', null, `${cartLines.reduce((count, line) => count + line.qty, 0)} article(s)`)
                ),
                cartLines.length
                  ? e(
                      'div',
                      { className: 'pos-cart-lines' },
                      ...cartLines.map(({ product, qty, amount }) =>
                        e(
                          'div',
                          { key: product.product_id, className: 'pos-cart-line' },
                          e('strong', null, product.gen_name),
                          e('span', null, money(product.price)),
                          e('input', {
                            'aria-label': `Quantité ${product.gen_name}`,
                            type: 'number',
                            min: 1,
                            max: availableQuantity(product),
                            value: qty,
                            onChange: (event) => updateCartQuantity(product, event.target.value),
                          }),
                          e('strong', null, money(amount)),
                          e('button', {
                            className: 'text-button danger-text',
                            type: 'button',
                            onClick: () => updateCartQuantity(product, 0),
                            'aria-label': `Retirer ${product.gen_name}`,
                          }, 'Retirer')
                        )
                      )
                    )
                  : e('p', { className: 'empty-state' }, 'Le panier est vide. Ajoutez des produits pour commencer.'),
                e('div', { className: 'pos-total' }, `Total : ${money(total)}`),
                e(
                  'form',
                  { onSubmit: checkout },
                  e(
                    'label',
                    null,
                    'Contexte de vente',
                    e(
                      'select',
                      {
                        value: selectedFairId,
                        onChange: (event) => {
                          const nextFairId = event.target.value;
                          const nextContext = fairContexts.find(
                            (context) => String(context.fair_id) === nextFairId
                          );
                          setSelectedFairId(nextFairId);
                          setCart({});
                          setSelectedSellerId(
                            nextContext?.sellers.length === 1
                              ? String(nextContext.sellers[0].user_id)
                              : ''
                          );
                          setError('');
                        },
                      },
                      e(
                        'option',
                        { value: '', disabled: true },
                        'Sélectionner une foire'
                      ),
                      fairContexts.map((context) =>
                        e('option', { key: context.fair_id, value: context.fair_id }, `Foire : ${context.fair_name}`)
                      )
                    )
                  ),
                  selectedFairContext
                    ? e(
                        'label',
                        null,
                        'Vendeur affecté',
                        e(
                          'select',
                          {
                            value: selectedSellerId,
                            onChange: (event) => setSelectedSellerId(event.target.value),
                            required: true,
                          },
                          e('option', { value: '', disabled: true }, 'Sélectionner le vendeur'),
                          selectedFairContext.sellers.map((seller) =>
                            e('option', { key: seller.user_id, value: seller.user_id }, seller.name)
                          )
                        )
                      )
                    : null,
                  selectedFairContext
                    ? e('div', {
                        style: {
                          margin: '8px 0 14px',
                          padding: '12px 16px',
                          background: '#f8fafc',
                          border: '1px solid #cbd5e1',
                          borderLeft: '4px solid #2563eb',
                          borderRadius: '8px',
                          fontSize: '13px',
                          boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                        }
                      },
                        e('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' } },
                          e('div', { style: { fontWeight: 700, color: '#1e40af', display: 'flex', alignItems: 'center', gap: '6px' } },
                            '🏪 Caisse Active : ',
                            e('span', { style: { fontFamily: 'monospace', background: '#1e40af', color: '#fff', padding: '2px 8px', borderRadius: '4px', fontSize: '12px' } },
                              selectedFairContext.register_code || ('CAISSE-F' + selectedFairContext.fair_id)
                            )
                          ),
                          e('span', { style: { fontSize: '11px', color: '#16a34a', fontWeight: 600, background: '#dcfce7', padding: '2px 6px', borderRadius: '4px' } }, '● Connectée au stock foire')
                        ),
                        e('div', { style: { display: 'flex', flexDirection: 'column', gap: '5px', color: '#334155', fontSize: '12px', borderTop: '1px solid #e2e8f0', paddingTop: '8px' } },
                          e('div', null, e('strong', null, '📦 Stock POS : '), 'Stand Laga ', e('span', { style: { fontWeight: 600, color: '#0f172a' } }, selectedFairContext.stand_name || 'Stand foire'), ' transporté vers la foire'),
                          e('div', null, e('strong', null, '🚗 Transporté avec voiture : '), e('span', { style: { fontWeight: 600, color: '#0f172a' } }, selectedFairContext.vehicle_name || 'Voiture assignée'), ' — Chauffeur : ', selectedFairContext.chauffeur_name || 'Chauffeur'),
                          selectedFairContext.mission_dates ? e('div', { style: { color: '#64748b' } }, '🗓️ Mission chauffeur (2 jours avant) : ', selectedFairContext.mission_dates) : null
                        ),
                        e('div', { style: { marginTop: '8px', fontSize: '11px', color: '#2563eb', fontWeight: 600, borderTop: '1px dashed #cbd5e1', paddingTop: '6px' } },
                          '✓ Les ventes effectuées sur cette caisse déduisent directement le stock de ce stand transporté.'
                        )
                      )
                    : e('p', { className: 'stock-help' }, 'Sélectionnez une foire pour ouvrir sa caisse et charger son stock transporté depuis le stand de Laga.'),
                  e(
                    'label',
                    null,
                    paymentType === 'credit' ? 'Nom du client' : 'Nom du client (facultatif)',
                    e('input', {
                      value: customerName,
                      maxLength: 160,
                      onChange: (event) => setCustomerName(event.target.value),
                      placeholder: 'Client comptoir',
                      required: paymentType === 'credit',
                    })
                  ),
                  e(
                    'label',
                    null,
                    'Mode de paiement',
                    e(
                      'select',
                      { value: paymentType, onChange: (event) => setPaymentType(event.target.value) },
                      e('option', { value: 'cash' }, 'Espèces'),
                      e('option', { value: 'credit' }, 'Crédit')
                    )
                  ),
                  paymentType === 'cash'
                    ? e(
                        'label',
                        null,
                        'Montant reçu',
                        e('input', {
                          type: 'number',
                          min: total,
                          step: '0.01',
                          value: cashReceived,
                          onChange: (event) => setCashReceived(event.target.value),
                          required: true,
                        }),
                        change !== null && change >= 0
                          ? e('span', { className: 'stock-help' }, `Monnaie à rendre : ${money(change)}`)
                          : null
                      )
                    : e(
                        'label',
                        null,
                        'Date d’échéance',
                        e('input', {
                          type: 'date',
                          value: dueDate,
                          onChange: (event) => setDueDate(event.target.value),
                          required: true,
                        })
                      ),
                  e('button', {
                    type: 'submit',
                    className: 'button',
                    disabled: saving || loading || !cartLines.length ||
                      !selectedFairId || !selectedSellerId,
                  }, saving ? 'Enregistrement...' : 'Valider la vente')
                )
              )
            )
          )
        : null,
      tab === 'history'
        ? e(
            'section',
            { className: 'panel' },
            e(
              'div',
              { className: 'panel-heading' },
              e('h2', null, 'Historique des ventes'),
              e('span', null, `${filteredSales.length} vente(s)`),
              user.type === 'admin' ? e('button', { className: 'button secondary small-button', onClick: function () { window.open(API_URL + '/pos/sales/export', '_blank'); } }, '\uD83D\uDCE5 Exporter CSV') : null
            ),
            e(
              'form',
              { className: 'pos-filter-form', onSubmit: searchSales },
              e('label', null, 'Du', e('input', {
                type: 'date',
                value: dateRange.from,
                onChange: (event) => setDateRange({ ...dateRange, from: event.target.value }),
              })),
              e('label', null, 'Au', e('input', {
                type: 'date',
                value: dateRange.to,
                onChange: (event) => setDateRange({ ...dateRange, to: event.target.value }),
              })),
              e('button', { className: 'button', type: 'submit', disabled: loading }, 'Filtrer')
            ),
            e('input', {
              className: 'search-input',
              type: 'search',
              placeholder: 'Rechercher par facture, client ou caissier...',
              value: saleSearch,
              onChange: (event) => setSaleSearch(event.target.value),
              'aria-label': 'Rechercher une vente',
            }),
            e(
              'div',
              { className: 'table-wrap' },
              e(
                'table',
                null,
                e('thead', null, e('tr', null,
                  e('th', null, 'Facture'),
                  e('th', null, 'Date'),
                  e('th', null, 'Client'),
                  e('th', null, 'Caissier'),
                  e('th', null, 'Paiement'),
                  e('th', null, 'Total'),
                  e('th', null, 'Solde'),
                  e('th', null, 'Reçu')
                )),
                e(
                  'tbody',
                  null,
                  filteredSales.length
                    ? filteredSales.map((sale) =>
                        e('tr', { key: sale.transaction_id },
                          e('td', null, sale.invoice_number),
                          e('td', null, sale.date),
                          e('td', null, sale.customer_name),
                          e('td', null,
                            sale.cashier,
                            sale.fair_name
                              ? e('small', { className: 'stock-help' }, `${sale.fair_name} · ${sale.seller_name}`)
                              : null
                          ),
                          e('td', null, sale.type === 'cash' ? 'Espèces' : 'Crédit'),
                          e('td', null, money(sale.amount)),
                          e('td', null, sale.type === 'credit' ? money(sale.balance) : '—'),
                          e('td', null, e('button', {
                            className: 'text-button',
                            onClick: () => showSale(sale),
                          }, 'Voir le reçu'))
                        )
                      )
                    : e('tr', null, e('td', { className: 'empty-state', colSpan: 9 },
                        loading ? 'Chargement des ventes...' : 'Aucune vente pour cette période.'))
                )
              )
            )
          )
        : null,
      selectedSale && tab === 'history'
        ? e(
            'section',
            { className: 'panel pos-receipt' },
            e(
              'div',
              { className: 'panel-heading' },
              e('h2', null, `Reçu ${selectedSale.invoice_number}`),
              e(
                'div',
                { className: 'receipt-actions no-print' },
                e('button', { className: 'button secondary small-button', onClick: () => window.print() }, 'Imprimer'),
                e('button', { className: 'text-button', onClick: () => setSelectedSale(null) }, 'Fermer')
              )
            ),
            e('p', null, `Date : ${selectedSale.date} · Caissier : ${selectedSale.cashier}`),
            selectedSale.fair_name
            ? e('p', null, `Foire : ${selectedSale.fair_name} · Vendeur : ${selectedSale.seller_name} · Opérateur : ${selectedSale.cashier_user_name || selectedSale.cashier}`)
            : null,
            e('p', null, `Client : ${selectedSale.customer_name}`),
            e(
              'div',
              { className: 'table-wrap' },
              e(
                'table',
                null,
                e('thead', null, e('tr', null,
                  e('th', null, 'Produit'),
                  e('th', null, 'Quantité'),
                  e('th', null, 'Prix'),
                  e('th', null, 'Montant')
                )),
                e(
                  'tbody',
                  null,
                  ...(selectedSale.items || []).map((item) =>
                    e('tr', { key: item.transaction_id },
                      e('td', null, `${item.product_code} — ${item.gen_name}`),
                      e('td', null, item.qty),
                      e('td', null, money(item.price)),
                      e('td', null, money(item.amount))
                    )
                  )
                )
              )
            ),
            e('h2', { className: 'pos-total' }, `Total : ${money(selectedSale.amount)}`),
            e('p', null, selectedSale.type === 'cash'
              ? `Payé : ${money(selectedSale.cash_received)} · Monnaie : ${money(selectedSale.change)}`
              : `À crédit · Échéance : ${selectedSale.due_date}`)
          )
        : null,
      tab === 'products' && isAdmin
        ? e(
            'div',
            { className: 'pos-layout' },
            e(
              'section',
              { className: 'panel' },
              e(
                'div',
                { className: 'panel-heading' },
                e('h2', null, 'Catalogue des produits'),
                e('span', null, `${products.filter((product) => product.qty < 10).length} stock(s) faible(s)`),
                e('button', {
                  className: 'button secondary small-button',
                  type: 'button',
                  disabled: saving,
                  onClick: importArticleProducts,
                }, 'Créer les produits depuis les articles')
              ),
              e('input', {
                className: 'search-input',
                type: 'search',
                id: 'pos-product-search',
                placeholder: 'Rechercher un produit (F2)...',
                value: productSearch,
                onChange: (event) => setProductSearch(event.target.value),
                'aria-label': 'Rechercher dans le catalogue',
              }),
              e(
                'div',
                { className: 'table-wrap' },
                e(
                  'table',
                  null,
                  e('thead', null, e('tr', null,
                    e('th', null, 'Code'),
                    e('th', null, 'Nom générique'),
                    e('th', null, 'Désignation'),
                    e('th', null, 'Coût'),
                    e('th', null, 'Prix'),
                    e('th', null, 'État des prix'),
                    e('th', null, 'Stock'),
                    e('th', null, 'Vendus'),
                    e('th', null, 'Actions')
                  )),
                  e(
                    'tbody',
                    null,
                    filteredProducts.length
                      ? filteredProducts.map((product) =>
                          e('tr', { key: product.product_id, className: product.qty < 10 ? 'low-stock-row' : undefined },
                            e('td', null, product.product_code),
                            e('td', null, product.gen_name),
                            e('td', null, product.product_name),
                            e('td', null, money(product.o_price)),
                            e('td', null, money(product.price)),
                            e('td', null, product.pricing_configured
                              ? 'Configurés'
                              : e('span', { className: 'notice error' }, 'À configurer')),
                            e('td', null, product.qty),
                            e('td', null, product.qty_sold),
                            e('td', { className: 'actions-cell' },
                              e('button', { className: 'text-button', onClick: () => startEditProduct(product) }, 'Modifier'),
                              e('button', { className: 'text-button danger-text', onClick: () => deleteProduct(product) }, 'Supprimer')
                            )
                          )
                        )
                      : e('tr', null, e('td', { className: 'empty-state', colSpan: 9 },
                          loading ? 'Chargement des produits...' : 'Aucun produit enregistré.'))
                  )
                )
              )
            ),
            e(
              'section',
              { className: 'panel form-panel' },
              e(
                'div',
                { className: 'panel-heading' },
                e('h2', null, editingProductId ? 'Modifier le produit' : 'Ajouter un produit'),
                editingProductId
                  ? e('button', { className: 'text-button', onClick: resetProductForm }, 'Annuler')
                  : null
              ),
              e(
                'form',
                { onSubmit: saveProduct },
                e(
                  'label',
                  null,
                  'Article du stock général (facultatif)',
                  e(
                    'select',
                    {
                      name: 'article_ref',
                      value: productForm.article_ref,
                      onChange: (event) => {
                        const article = linkedArticles.find(
                          (item) => item.ref === event.target.value
                        );
                        setProductForm({
                          ...productForm,
                          article_ref: event.target.value,
                          ...(article
                            ? {
                                product_code: article.ref,
                                gen_name: article.nom,
                                qty: String(article.v_stocks),
                              }
                            : {}),
                        });
                      },
                    },
                    e('option', { value: '' }, 'Catalogue POS séparé'),
                    ...linkedArticles.map((article) =>
                      e(
                        'option',
                        { key: article.ref, value: article.ref },
                        `${article.ref} — ${article.nom} (stock : ${article.v_stocks})`
                      )
                    )
                  )
                ),
                e('label', null, 'Code-barres',
                  e('div', { style: { display: 'flex', gap: '6px' } },
                    e('input', {
                      value: productForm.barcode,
                      placeholder: 'Code-barres EAN / 128...',
                      onChange: (e) => setProductForm({ ...productForm, barcode: e.target.value }),
                      style: { flex: 1, fontFamily: 'monospace' }
                    }),
                    e('button', {
                      type: 'button',
                      className: 'button secondary small-button',
                      style: { whiteSpace: 'nowrap' },
                      onClick: () => {
                        const generated = '200' + Math.floor(100000000 + Math.random() * 900000000);
                        setProductForm({ ...productForm, barcode: generated });
                      }
                    }, '⚡ Générer')
                  )
                ),
                ...[
                  ['product_code', 'Code / marque', 'text'],
                  ['gen_name', 'Nom générique', 'text'],
                  ['product_name', 'Catégorie / description', 'text'],
                  ['supplier', 'Fournisseur', 'text'],
                  ['date_arrival', 'Date de réception', 'date'],
                  ['expiry_date', 'Date d’expiration', 'date'],
                  ['o_price', 'Prix de revient', 'number'],
                  ['price', 'Prix de vente', 'number'],
                  ['qty', 'Stock disponible', 'number'],
                ].map(([field, label, type]) =>
                  e(
                    'label',
                    { key: field },
                    label,
                    e('input', {
                      name: field,
                      type,
                      min: type === 'number' ? 0 : undefined,
                      step: type === 'number' && field !== 'qty' ? '0.01' : undefined,
                      value: productForm[field],
                      onChange: (event) => setProductForm({
                        ...productForm,
                        [field]: event.target.value,
                      }),
                      required: ['product_code', 'gen_name', 'o_price', 'price', 'qty'].includes(field),
                    })
                  )
                ),
                e('label', { className: 'checkbox-label' },
                  e('input', {
                    type: 'checkbox',
                    checked: Boolean(productForm.pricing_configured),
                    onChange: (event) => setProductForm({
                      ...productForm,
                      pricing_configured: event.target.checked,
                    }),
                  }),
                  'Prix configurés (autoriser la vente)'
                ),
                !productForm.pricing_configured
                  ? e('p', { className: 'stock-help' }, 'Ce produit ne sera pas vendu tant que ses prix ne sont pas configurés et que cette option n’est pas activée.')
                  : null,
                e('p', { className: 'stock-help' }, productForm.article_ref
                  ? 'Produit lié : le stock affiché est partagé. Les ventes, achats, ajustements POS et mouvements du stock général mettent à jour la même quantité.'
                  : 'Les quantités vendues sont calculées par la caisse. Le stock est diminué lors de la validation de la vente.'),
                e('button', {
                  type: 'submit',
                  className: 'button',
                  disabled: saving,
                }, saving ? 'Enregistrement...' : editingProductId ? 'Enregistrer les changements' : 'Créer le produit')
              )
            )
          )
        : null
      ,
      tab === 'purchases' && isAdmin
          ? e(
              'div',
              { className: 'pos-layout' },
              e(
                'section',
                { className: 'panel' },
                e(
                  'div',
                  { className: 'panel-heading' },
                  e('h2', null, 'Historique des achats'),
                  e('span', null, `${purchases.length} achat(s)`)
                ),
                e(
                  'div',
                  { className: 'table-wrap' },
                  e(
                    'table',
                    null,
                    e('thead', null, e('tr', null,
                      e('th', null, 'Facture'),
                      e('th', null, 'Date'),
                      e('th', null, 'Fournisseur'),
                      e('th', null, 'Remarques'),
                      e('th', null, 'Total'),
                      e('th', null, 'Détail')
                    )),
                    e(
                      'tbody',
                      null,
                      purchases.length
                        ? purchases.map((purchase) =>
                            e('tr', { key: purchase.purchase_id },
                              e('td', null, purchase.invoice_number),
                              e('td', null, purchase.date),
                              e('td', null, purchase.supplier),
                              e('td', null, purchase.remarks),
                              e('td', null, money(purchase.total)),
                              e('td', null, e('button', {
                                className: 'text-button',
                                onClick: () => showPurchase(purchase),
                              }, 'Voir'))
                            )
                          )
                        : e('tr', null, e('td', { className: 'empty-state', colSpan: 6 },
                            loading ? 'Chargement des achats...' : 'Aucun achat enregistré.'))
                    )
                  )
                ),
                selectedPurchase
                  ? e(
                      'div',
                      { className: 'pos-receipt' },
                      e(
                        'div',
                        { className: 'panel-heading' },
                        e('h3', null, `Achat ${selectedPurchase.invoice_number}`),
                        e('button', { className: 'text-button', onClick: () => setSelectedPurchase(null) }, 'Fermer')
                      ),
                      e('p', null, `${selectedPurchase.date} · ${selectedPurchase.supplier}`),
                      e(
                        'div',
                        { className: 'table-wrap' },
                        e(
                          'table',
                          null,
                          e('thead', null, e('tr', null,
                            e('th', null, 'Produit'),
                            e('th', null, 'Quantité'),
                            e('th', null, 'Coût unitaire'),
                            e('th', null, 'Total')
                          )),
                          e(
                            'tbody',
                            null,
                            ...(selectedPurchase.items || []).map((item) =>
                              e('tr', { key: item.purchase_item_id },
                                e('td', null, `${item.product_code} — ${item.gen_name}`),
                                e('td', null, item.qty),
                                e('td', null, money(item.unit_cost)),
                                e('td', null, money(item.total_cost))
                              )
                            )
                          )
                        )
                      ),
                      e('strong', null, `Total achat : ${money(selectedPurchase.total)}`),
                      selectedPurchase.remarks ? e('p', null, selectedPurchase.remarks) : null
                    )
                  : null
              ),
              e(
                'section',
                { className: 'panel form-panel' },
                e(
                  'div',
                  { className: 'panel-heading' },
                  e('h2', null, 'Enregistrer un achat')
                ),
                e(
                  'form',
                  { onSubmit: savePurchase },
                  e('label', null, 'Numéro de facture', e('input', {
                    value: purchaseForm.invoice_number,
                    maxLength: 120,
                    onChange: (event) => setPurchaseForm({ ...purchaseForm, invoice_number: event.target.value }),
                    required: true,
                  })),
                  e('label', null, 'Date', e('input', {
                    type: 'date',
                    value: purchaseForm.date,
                    onChange: (event) => setPurchaseForm({ ...purchaseForm, date: event.target.value }),
                    required: true,
                  })),
                  e('label', null, 'Fournisseur', e('input', {
                    value: purchaseForm.supplier,
                    maxLength: 160,
                    onChange: (event) => setPurchaseForm({ ...purchaseForm, supplier: event.target.value }),
                    required: true,
                  })),
                  e('label', null, 'Remarques', e('input', {
                    value: purchaseForm.remarks,
                    maxLength: 500,
                    onChange: (event) => setPurchaseForm({ ...purchaseForm, remarks: event.target.value }),
                  })),
                  e(
                    'div',
                    { className: 'purchase-line-fields' },
                    e('label', null, 'Produit', e(
                      'select',
                      {
                        value: purchaseDraft.product_id,
                        onChange: (event) => {
                          const product = products.find((item) => item.product_id === Number(event.target.value));
                          setPurchaseDraft({
                            ...purchaseDraft,
                            product_id: event.target.value,
                            unit_cost: product ? String(product.o_price) : '',
                          });
                        },
                      },
                      e('option', { value: '' }, 'Sélectionner un produit'),
                      products.map((product) => e('option', {
                        key: product.product_id,
                        value: product.product_id,
                      }, `${product.product_code} — ${product.gen_name}`))
                    )),
                    e('label', null, 'Quantité', e('input', {
                      type: 'number',
                      min: 1,
                      step: 1,
                      value: purchaseDraft.qty,
                      onChange: (event) => setPurchaseDraft({ ...purchaseDraft, qty: event.target.value }),
                    })),
                    e('label', null, 'Coût unitaire', e('input', {
                      type: 'number',
                      min: 0,
                      step: '0.01',
                      value: purchaseDraft.unit_cost,
                      onChange: (event) => setPurchaseDraft({ ...purchaseDraft, unit_cost: event.target.value }),
                    })),
                    e('button', { type: 'button', className: 'button secondary', onClick: addPurchaseLine }, 'Ajouter au bon')
                  )
                ),
                purchaseItems.length
                  ? e(
                      'div',
                      { className: 'table-wrap' },
                      e(
                        'table',
                        null,
                        e('thead', null, e('tr', null,
                          e('th', null, 'Produit'),
                          e('th', null, 'Qté'),
                          e('th', null, 'Coût unitaire'),
                          e('th', null, 'Total'),
                          e('th', null, 'Action')
                        )),
                        e(
                          'tbody',
                          null,
                          ...purchaseItems.map((item) =>
                            e('tr', { key: item.product_id },
                              e('td', null, `${item.product_code} — ${item.gen_name}`),
                              e('td', null, item.qty),
                              e('td', null, money(item.unit_cost)),
                              e('td', null, money(item.qty * item.unit_cost)),
                              e('td', null, e('button', {
                                className: 'text-button danger-text',
                                onClick: () => setPurchaseItems((current) =>
                                  current.filter((line) => line.product_id !== item.product_id)
                                ),
                              }, 'Retirer'))
                            )
                          )
                        )
                      ),
                      e('h3', { className: 'pos-total' }, `Total : ${money(purchaseItems.reduce((sum, item) => sum + item.qty * item.unit_cost, 0))}`)
                    )
                  : e('p', { className: 'empty-state' }, 'Ajoutez des produits pour préparer le bon d’achat.'),
                e('button', {
                  type: 'button',
                  className: 'button',
                  disabled: saving || !purchaseItems.length,
                  onClick: (event) => {
                    const form = event.currentTarget.closest('.form-panel').querySelector('form');
                    if (form.reportValidity()) {
                      savePurchase({ preventDefault: () => {} });
                    }
                  },
                }, saving ? 'Enregistrement...' : 'Valider l’achat et mettre à jour le stock')
              )
            )
          : null,
      tab === 'report' && isAdmin
          ? e(
              'section',
              { className: 'panel' },
              e(
                'div',
                { className: 'panel-heading' },
                e('h2', null, 'Rapport des ventes'),
                salesReport ? e('span', null, `${salesReport.count} vente(s)`) : null
              ),
              e(
                'form',
                { className: 'pos-filter-form', onSubmit: searchSalesReport },
                e('label', null, 'Du', e('input', {
                  type: 'date',
                  value: dateRange.from,
                  onChange: (event) => setDateRange({ ...dateRange, from: event.target.value }),
                })),
                e('label', null, 'Au', e('input', {
                  type: 'date',
                  value: dateRange.to,
                  onChange: (event) => setDateRange({ ...dateRange, to: event.target.value }),
                })),
                e('label', null, 'Foire', e('select', {
                  value: reportFairId,
                  onChange: (event) => {
                    setReportFairId(event.target.value);
                    setReportSellerId('');
                  },
                },
                e('option', { value: '' }, 'Toutes les ventes'),
                fairContexts.map((context) =>
                  e('option', { key: context.fair_id, value: context.fair_id }, context.fair_name)
                ))),
                selectedReportFairContext
                  ? e('label', null, 'Vendeur', e('select', {
                      value: reportSellerId,
                      onChange: (event) => setReportSellerId(event.target.value),
                    },
                    e('option', { value: '' }, 'Tous les vendeurs'),
                    selectedReportFairContext.sellers.map((seller) =>
                      e('option', { key: seller.user_id, value: seller.user_id }, seller.name)
                    )))
                  : null,
                e('button', { className: 'button', type: 'submit', disabled: loading }, 'Filtrer'),
                e('button', { className: 'button secondary', type: 'button', onClick: () => window.print() }, 'Imprimer')
              ),
              salesReport
                ? e(
                    React.Fragment,
                    null,
                    e(
                      'div',
                      { className: 'pos-summary' },
                      e('div', { className: 'panel' }, e('span', null, 'Nombre de ventes'), e('h2', null, salesReport.count)),
                      e('div', { className: 'panel' }, e('span', null, 'Chiffre d’affaires'), e('h2', null, money(salesReport.total_amount))),
                      e('div', { className: 'panel' }, e('span', null, 'Marge totale'), e('h2', null, money(salesReport.total_profit)))
                    ),
                    e(
                      'div',
                      { className: 'table-wrap' },
                      e(
                        'table',
                        null,
                        e('thead', null, e('tr', null,
                          e('th', null, 'N°'),
                          e('th', null, 'Date'),
                          e('th', null, 'Client'),
                          e('th', null, 'Foire / vendeur'),
                          e('th', null, 'Facture'),
                          e('th', null, 'Paiement'),
                          e('th', null, 'Montant'),
                          e('th', null, 'Marge')
                        )),
                        e(
                          'tbody',
                          null,
                          salesReport.sales.length
                            ? salesReport.sales.map((sale) =>
                                e('tr', { key: sale.transaction_id },
                                  e('td', null, `STI-00${sale.transaction_id}`),
                                  e('td', null, sale.date),
                                  e('td', null, sale.customer_name),
                                  e('td', null, sale.fair_name
                                    ? `${sale.fair_name} / ${sale.seller_name}`
                                    : 'Vente générale'),
                                  e('td', null, sale.invoice_number),
                                  e('td', null, sale.type === 'cash' ? 'Espèces' : 'Crédit'),
                                  e('td', null, money(sale.amount)),
                                  e('td', null, money(sale.profit))
                                )
                              )
                            : e('tr', null, e('td', { className: 'empty-state', colSpan: 8 }, 'Aucune vente pour cette période.'))
                        )
                      )
                    )
                  )
                : e('p', { className: 'empty-state' }, loading ? 'Chargement du rapport...' : 'Aucune donnée à afficher.')
            )
          : null,
      tab === 'fair-report' && isAdmin
        ? e(
            'section',
            { className: 'panel' },
            e(
              'div',
              { className: 'panel-heading' },
              e('h2', null, 'Performance des foires'),
              fairReport ? e('span', null, `${fairReport.count} vente(s) en foire`) : null
            ),
            e(
              'form',
              { className: 'pos-filter-form', onSubmit: searchFairReport },
              e('label', null, 'Du', e('input', {
                type: 'date',
                value: dateRange.from,
                onChange: (event) => setDateRange({ ...dateRange, from: event.target.value }),
              })),
              e('label', null, 'Au', e('input', {
                type: 'date',
                value: dateRange.to,
                onChange: (event) => setDateRange({ ...dateRange, to: event.target.value }),
              })),
              e('button', { className: 'button', type: 'submit', disabled: loading }, 'Filtrer'),
              e('button', {
                className: 'button secondary',
                type: 'button',
                onClick: () => window.print(),
              }, 'Imprimer')
            ),
            fairReport
              ? e(
                  React.Fragment,
                  null,
                  e(
                    'div',
                    { className: 'pos-summary' },
                    e('div', { className: 'panel' },
                      e('span', null, 'Ventes en foire'),
                      e('h2', null, fairReport.count)
                    ),
                    e('div', { className: 'panel' },
                      e('span', null, 'Chiffre d’affaires en foire'),
                      e('h2', null, money(fairReport.total_amount))
                    ),
                    e('div', { className: 'panel' },
                      e('span', null, 'Marge en foire'),
                      e('h2', null, money(fairReport.total_profit))
                    )
                  ),
                  e(
                    'div',
                    { className: 'table-wrap' },
                    e(
                      'table',
                      null,
                      e('thead', null, e('tr', null,
                        e('th', null, 'Foire'),
                        e('th', null, 'Vendeur'),
                        e('th', null, 'Ventes'),
                        e('th', null, 'Chiffre d’affaires'),
                        e('th', null, 'Marge')
                      )),
                      e(
                        'tbody',
                        null,
                        fairReport.fairs.flatMap((fair) =>
                          fair.sellers.length
                            ? fair.sellers.map((seller) =>
                                e('tr', {
                                  key: `${fair.fair_id}-${seller.seller_id}`,
                                },
                                e('td', null, fair.fair_name),
                                e('td', null, seller.seller_name),
                                e('td', null, seller.count),
                                e('td', null, money(seller.total_amount)),
                                e('td', null, money(seller.total_profit)))
                              )
                            : [e('tr', { key: `${fair.fair_id}-empty` },
                                e('td', null, fair.fair_name),
                                e('td', null, '—'),
                                e('td', null, 0),
                                e('td', null, money(0)),
                                e('td', null, money(0)))]
                            )
                        ),
                        e('tr', { key: 'general-sales' },
                          e('td', null, 'Ventes générales'),
                          e('td', null, '—'),
                          e('td', null, fairReport.general_sales.count),
                          e('td', null, money(fairReport.general_sales.total_amount)),
                          e('td', null, money(fairReport.general_sales.total_profit))
                        )
                      )
                    )
                  )
                : e('p', { className: 'empty-state' },
                  loading ? 'Chargement du rapport...' : 'Aucune donnée à afficher.')
          )
        : null,
      tab === 'receivables'
        ? e(
            'section',
            { className: 'panel' },
            e(
              'div',
              { className: 'panel-heading' },
              e('h2', null, 'Crédits clients à recouvrer'),
              e('span', null, `${receivables.length} facture(s)`)
            ),
            e(
              'form',
              { className: 'pos-filter-form', onSubmit: searchReceivables },
              e('label', null, 'Du', e('input', {
                type: 'date',
                value: dateRange.from,
                onChange: (event) => setDateRange({ ...dateRange, from: event.target.value }),
              })),
              e('label', null, 'Au', e('input', {
                type: 'date',
                value: dateRange.to,
                onChange: (event) => setDateRange({ ...dateRange, to: event.target.value }),
              })),
              e('button', { className: 'button', type: 'submit', disabled: loading }, 'Filtrer')
            ),
            e(
              'div',
              { className: 'pos-summary' },
              e('div', { className: 'panel' }, e('span', null, 'Factures impayées'), e('h2', null, receivables.length)),
              e('div', { className: 'panel' }, e('span', null, 'Solde à recevoir'), e('h2', null, money(receivables.reduce((sum, sale) => sum + sale.balance, 0))))
            ),
            e(
              'div',
              { className: 'table-wrap' },
              e(
                'table',
                null,
                e('thead', null, e('tr', null,
                  e('th', null, 'Date'),
                  e('th', null, 'Client'),
                  e('th', null, 'Facture'),
                  e('th', null, 'Échéance'),
                  e('th', null, 'Montant initial'),
                  e('th', null, 'Déjà payé'),
                  e('th', null, 'Solde'),
                  e('th', null, 'Action')
                )),
                e(
                  'tbody',
                  null,
                  receivables.length
                    ? receivables.map((sale) =>
                        e('tr', { key: sale.transaction_id },
                          e('td', null, sale.date),
                          e('td', null, sale.customer_name),
                          e('td', null, sale.invoice_number),
                          e('td', null, sale.due_date),
                          e('td', null, money(sale.amount)),
                          e('td', null, money(sale.paid_amount)),
                          e('td', null, money(sale.balance)),
                          e('td', null, e('button', {
                            className: 'text-button',
                            onClick: () => {
                              setPaymentAmount('');
                              setPaymentDate(new Date().toISOString().slice(0, 10));
                              showSale(sale);
                            },
                          }, 'Encaisser / ledger'))
                        )
                      )
                    : e('tr', null, e('td', { className: 'empty-state', colSpan: 8 },
                        loading ? 'Chargement des créances...' : 'Aucun crédit impayé pour cette période.'))
                )
              )
            ),
            selectedSale && selectedSale.type === 'credit'
              ? e(
                  'div',
                  { className: 'panel pos-receipt' },
                  e(
                    'div',
                    { className: 'panel-heading' },
                    e('h3', null, `Grand livre · ${selectedSale.customer_name} · ${selectedSale.invoice_number}`),
                    e('button', { className: 'text-button', onClick: () => setSelectedSale(null) }, 'Fermer')
                  ),
                  e('p', null, `Total facture : ${money(selectedSale.amount)} · Déjà encaissé : ${money(selectedSale.paid_amount)} · Solde : ${money(selectedSale.balance)}`),
                  (selectedSale.collections || []).length
                    ? e(
                        'div',
                        { className: 'table-wrap' },
                        e(
                          'table',
                          null,
                          e('thead', null, e('tr', null,
                            e('th', null, 'Date'),
                            e('th', null, 'Référence encaissement'),
                            e('th', null, 'Montant'),
                            e('th', null, 'Remarques')
                          )),
                          e(
                            'tbody',
                            null,
                            ...selectedSale.collections.map((collection) =>
                              e('tr', { key: collection.collection_id },
                                e('td', null, collection.date),
                                e('td', null, collection.invoice_number),
                                e('td', null, money(collection.amount)),
                                e('td', null, collection.remarks)
                              )
                            )
                          )
                        )
                      )
                    : e('p', { className: 'empty-state' }, 'Aucun encaissement enregistré pour cette facture.'),
                  selectedSale.balance > 0
                    ? e(
                        'form',
                        { className: 'pos-filter-form', onSubmit: collectPayment },
                        e('label', null, 'Montant encaissé', e('input', {
                          type: 'number',
                          min: '0.01',
                          max: selectedSale.balance,
                          step: '0.01',
                          value: paymentAmount,
                          onChange: (event) => setPaymentAmount(event.target.value),
                          required: true,
                        })),
                        e('label', null, 'Date', e('input', {
                          type: 'date',
                          value: paymentDate,
                          onChange: (event) => setPaymentDate(event.target.value),
                          required: true,
                        })),
                        e('label', null, 'Remarques', e('input', {
                          value: paymentRemarks,
                          maxLength: 500,
                          onChange: (event) => setPaymentRemarks(event.target.value),
                        })),
                        e('button', { className: 'button', type: 'submit', disabled: saving }, saving ? 'Enregistrement...' : 'Enregistrer l’encaissement')
                      )
                    : e('p', { className: 'notice success' }, 'Cette facture est entièrement réglée.')
                )
              : null
          )
        : null,
      tab === 'collections'
        ? e(
            'section',
            { className: 'panel' },
            e(
              'div',
              { className: 'panel-heading' },
              e('h2', null, 'Rapport des encaissements'),
              collectionSummary ? e('span', null, `${collectionSummary.count} règlement(s)`) : null
            ),
            e(
              'form',
              { className: 'pos-filter-form', onSubmit: searchCollections },
              e('label', null, 'Du', e('input', {
                type: 'date',
                value: dateRange.from,
                onChange: (event) => setDateRange({ ...dateRange, from: event.target.value }),
              })),
              e('label', null, 'Au', e('input', {
                type: 'date',
                value: dateRange.to,
                onChange: (event) => setDateRange({ ...dateRange, to: event.target.value }),
              })),
              e('button', { className: 'button', type: 'submit', disabled: loading }, 'Filtrer'),
              e('button', { className: 'button secondary', type: 'button', onClick: () => window.print() }, 'Imprimer')
            ),
            collectionSummary
              ? e('div', { className: 'pos-summary' },
                  e('div', { className: 'panel' }, e('span', null, 'Nombre d’encaissements'), e('h2', null, collectionSummary.count)),
                  e('div', { className: 'panel' }, e('span', null, 'Total encaissé'), e('h2', null, money(collectionSummary.total_amount)))
                )
              : null,
            e(
              'div',
              { className: 'table-wrap' },
              e(
                'table',
                null,
                e('thead', null, e('tr', null,
                  e('th', null, 'Référence'),
                  e('th', null, 'Date'),
                  e('th', null, 'Client'),
                  e('th', null, 'Facture de vente'),
                  e('th', null, 'Montant'),
                  e('th', null, 'Remarques')
                )),
                e(
                  'tbody',
                  null,
                  collections.length
                    ? collections.map((collection) =>
                        e('tr', { key: collection.collection_id },
                          e('td', null, collection.invoice_number),
                          e('td', null, collection.date),
                          e('td', null, collection.customer_name),
                          e('td', null, collection.sale_invoice),
                          e('td', null, money(collection.amount)),
                          e('td', null, collection.remarks)
                        )
                      )
                    : e('tr', null, e('td', { className: 'empty-state', colSpan: 6 },
                        loading ? 'Chargement des encaissements...' : 'Aucun encaissement pour cette période.'))
                )
              )
            )
          )
        : null
    )
  );
}

const EMPTY_MOVEMENT = {
  type: 'reception',
  article_ref: '',
  quantite: '1',
  date_mouvement: new Date().toISOString().slice(0, 10),
  id_fournisseur: '',
  id_client: '',
};
const MOVEMENT_TYPES = [
  ['reception', 'Réception'],
  ['achat', 'Achat'],
  ['livraison', 'Livraison'],
  ['vente', 'Vente'],
];
const RESOURCE_PAGES = {
  vehicles: {
    title: 'Parc automobile',
    singular: 'Véhicule',
    endpoint: 'vehicles',
    fields: [
      ['model', 'Modèle', 'text'],
      ['immatricule', 'Immatriculation', 'text'],
      ['annee', 'Année', 'number'],
      ['puissance', 'Puissance', 'number'],
      ['location', 'Véhicule en location', 'checkbox'],
      ['date_d_loc', 'Début de location', 'date'],
      ['date_f_loc', 'Fin de location', 'date'],
    ],
    columns: ['model', 'immatricule', 'annee', 'puissance', 'location', 'date_d_loc', 'date_f_loc'],
  },
  fairs: {
    title: 'Foires',
    singular: 'Foire',
    endpoint: 'fairs',
    optional: [
      'organizer',
      'start_date',
      'end_date',
      'product_send_deadline',
      'assigned_vehicle_id',
      'status',
      'allow_late_send',
      'late_send_reason',
      'manager_notes',
      'auto_assign',
    ],
    fields: [
      ['nom', 'Nom', 'text'],
      ['ville', 'Ville', 'text'],
      ['adresse', 'Adresse', 'text'],
      ['contact', 'Contact', 'text'],
      ['d_limite', 'Date limite', 'date'],
      ['type', 'Type', 'select'],
      ['organizer', 'Organisateur', 'text'],
      ['start_date', 'Début de la foire', 'date'],
      ['end_date', 'Fin de la foire', 'date'],
      ['product_send_deadline', 'Date limite d’envoi des produits', 'date'],
      ['assigned_vehicle_id', 'Véhicule préféré (facultatif)', 'lookup'],
      ['status', 'Statut', 'fair-status'],
      ['allow_late_send', 'Autoriser un envoi tardif', 'checkbox'],
      ['late_send_reason', 'Justification de l’envoi tardif', 'text'],
      ['manager_notes', 'Notes du responsable', 'textarea'],
      ['auto_assign', 'Automatisation complète (mission chauffeur 2j avant, vendeur, décorateur, stand Laga, stock & caisse)', 'checkbox'],
    ],
    columns: [
      'nom', 'type', 'ville', 'adresse', 'contact', 'd_limite', 'vehicle_name', 'organizer',
      'start_date', 'end_date', 'product_send_deadline', 'status', 'allow_late_send',
    ],
  },
  'stand-types': {
    title: 'Types de stands',
    singular: 'Type de stand',
    endpoint: 'stand-types',
    fields: [
      ['type', 'Type', 'text'],
      ['etat', 'État', 'text'],
    ],
    columns: ['id', 'type', 'etat'],
  },
  'stand-inventory': {
    title: 'Articles des stands',
    singular: 'Article de stand',
    endpoint: 'stand-inventory',
    fields: [
      ['id_stand', 'Type de stand', 'lookup'],
      ['ref_article', 'Article', 'lookup'],
      ['quantite', 'Quantité', 'number'],
      ['date_ch', 'Date', 'date'],
    ],
    columns: ['id', 'stand_type', 'article_nom', 'quantite', 'date_ch'],
  },
  permissions: {
    title: 'Droits par rôle',
    singular: 'profil d’accès',
    endpoint: 'permissions',
    key: 'type_user',
    fields: [
      ['type_user', 'Type utilisateur', 'role'],
      ['foire', 'Foire', 'checkbox'],
      ['stand', 'Stand', 'checkbox'],
      ['liste_stand', 'Liste des stands', 'checkbox'],
      ['article', 'Article', 'checkbox'],
      ['work', 'Mission', 'checkbox'],
      ['fournisseur', 'Fournisseur', 'checkbox'],
      ['client', 'Client', 'checkbox'],
      ['reservation', 'Réservation', 'checkbox'],
      ['empl', 'Employés', 'checkbox'],
      ['voiture', 'Véhicule', 'checkbox'],
      ['mouvement', 'Mouvement', 'checkbox'],
      ['livraison', 'Livraison', 'checkbox'],
      ['reception', 'Réception', 'checkbox'],
      ['vente', 'Vente', 'checkbox'],
      ['achat', 'Achat', 'checkbox'],
    ],
    columns: [
      'type_user', 'foire', 'stand', 'liste_stand', 'article', 'work',
      'fournisseur', 'client', 'reservation', 'empl', 'voiture',
      'mouvement', 'livraison', 'reception', 'vente', 'achat',
    ],
  },
  employees: {
    title: 'Employés',
    singular: 'employé',
    endpoint: 'employees',
    readOnly: true,
    fields: [
      ['prenom', 'Prénom', 'text'],
      ['nom', 'Nom', 'text'],
      ['login', 'Identifiant', 'text'],
      ['type', 'Rôle', 'text'],
      ['ville', 'Ville', 'text'],
    ],
    columns: ['id', 'prenom', 'nom', 'login', 'type', 'ville'],
  },
  reservations: {
    title: 'Réservations',
    singular: 'Réservation',
    endpoint: 'reservations',
    fields: [
      ['id_agent', 'Agent', 'lookup'],
      ['id_foire', 'Foire', 'lookup'],
      ['taille_stand', 'Taille du stand', 'text'],
      ['logement', 'Logement', 'text'],
      ['date_d', 'Date de début', 'date'],
      ['date_f', 'Date de fin', 'date'],
      ['etat', 'État', 'select'],
      ['date_c', 'Date de confirmation', 'date'],
    ],
    columns: ['id', 'agent_nom', 'foire_nom', 'taille_stand', 'logement', 'date_d', 'date_f', 'etat', 'date_c'],
  },
  works: {
    title: 'Missions et confirmations',
    singular: 'Mission',
    endpoint: 'works',
    fields: [
      ['date_d', 'Date de début', 'date'],
      ['date_f', 'Date de fin', 'date'],
      ['id_foire', 'Foire', 'lookup'],
      ['id_stand', 'Type de stand', 'lookup'],
      ['id_vendeur', 'Vendeur', 'lookup'],
      ['id_deco', 'Décorateur', 'lookup'],
      ['id_chauffeur', 'Chauffeur', 'lookup'],
      ['id_voiture', 'Véhicule', 'lookup'],
      ['flow', 'État', 'select'],
    ],
    columns: ['id', 'date_d', 'date_f', 'foire_nom', 'stand_type', 'vendeur_nom', 'deco_nom', 'chauffeur_nom', 'voiture_nom', 'flow'],
  },
};

function StockPage({ user, onBack, onArticles, onSuppliers, onLogout }) {
  const allowedMovementTypes = MOVEMENT_TYPES.filter(([type]) =>
    canManageMovement(user, type)
  );
  const canManageStock = allowedMovementTypes.length > 0;
  const [articles, setArticles] = useState([]);
  const [clients, setClients] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [movements, setMovements] = useState([]);
  const [form, setForm] = useState({
    ...EMPTY_MOVEMENT,
    type: allowedMovementTypes[0]?.[0] || EMPTY_MOVEMENT.type,
  });
  const [editingId, setEditingId] = useState(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function refreshData() {
    const [articleRows, clientRows, supplierRows, movementRows] = await Promise.all([
      api('/articles'),
      api('/clients'),
      api('/suppliers'),
      api('/stock/movements'),
    ]);
    setArticles(articleRows);
    setClients(clientRows);
    setSuppliers(supplierRows);
    setMovements(movementRows);
  }

  useEffect(() => {
    refreshData()
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  const incoming = form.type === 'reception' || form.type === 'achat';
  const hasParty = incoming ? suppliers.length > 0 : clients.length > 0;

  function resetForm() {
    setEditingId(null);
    setForm({
      ...EMPTY_MOVEMENT,
      type: allowedMovementTypes[0]?.[0] || EMPTY_MOVEMENT.type,
      article_ref: articles[0]?.ref || '',
    });
  }

  function startEdit(movement) {
    setEditingId(movement.id);
    setForm({
      type: movement.type,
      article_ref: movement.article_ref,
      quantite: String(movement.quantite),
      date_mouvement: movement.date_mouvement,
      id_fournisseur: movement.id_fournisseur ? String(movement.id_fournisseur) : '',
      id_client: movement.id_client ? String(movement.id_client) : '',
    });
    setMessage('');
    setError('');
  }

  async function saveMovement(event) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    setError('');
    const formData = new FormData(event.currentTarget);
    const type = formData.get('type');
    const payload = {
      type,
      article_ref: formData.get('article_ref'),
      quantite: Number(formData.get('quantite')),
      date_mouvement: formData.get('date_mouvement'),
    };
    if (type === 'reception' || type === 'achat') {
      payload.id_fournisseur = Number(formData.get('id_fournisseur'));
    } else {
      payload.id_client = Number(formData.get('id_client'));
    }

    try {
      const path = editingId ? `/stock/movements/${editingId}` : '/stock/movements';
      const data = await api(path, {
        method: editingId ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      });
      setMessage(data.message);
      resetForm();
      await refreshData();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function deleteMovement(movement) {
    if (!window.confirm(`Annuler le mouvement #${movement.id} (${movement.type}, ${movement.quantite}) ?`)) {
      return;
    }
    setMessage('');
    setError('');
    try {
      const data = await api(`/stock/movements/${movement.id}`, { method: 'DELETE' });
      setMessage(data.message);
      await refreshData();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  const filteredMovements = movements.filter((movement) =>
    `${movement.id} ${movement.type} ${movement.article_ref} ${movement.article_nom} ${movement.fournisseur_nom || ''} ${movement.client_nom || ''} ${movement.date_mouvement}`
      .toLowerCase()
      .includes(search.toLowerCase())
  );

  return e(
    'main',
    { className: 'dashboard' },
    e(
      'header',
      { className: 'topbar' },
      e(
        'div',
        null,
        e('strong', null, 'OKBA INTER'),
        e('span', { className: 'topbar-label' }, 'Gestion de stock')
      ),
      e(
        'div',
        { className: 'topbar-user' },
        user.type === 'admin'
          ? e('button', { className: 'button secondary small-button', onClick: onBack }, 'Utilisateurs')
          : null,
        e('button', { className: 'button secondary small-button', onClick: onArticles }, 'Articles'),
        hasViewPermission(user, 'fournisseur')
          ? e('button', { className: 'button secondary small-button', onClick: onSuppliers }, 'Fournisseurs')
          : null,
        e('span', null, `${user.prenom} ${user.nom}`),
        e('button', { className: 'button secondary small-button', onClick: onLogout }, 'Déconnexion')
      )
    ),
    e(
      'div',
      { className: 'content' },
      e(
        'div',
        { className: 'page-heading' },
        e(
          'div',
          null,
          e('p', { className: 'eyebrow' }, 'GESTION COMMERCIALE'),
          e('h1', null, 'Réceptions et livraisons'),
          e('p', { className: 'subtitle' }, 'Enregistrez les entrées et sorties et consultez l’historique du stock.')
        ),
        e('span', { className: 'count-badge' }, `${movements.length} mouvement${movements.length === 1 ? '' : 's'}`)
      ),
      message ? e('p', { className: 'notice success', role: 'status' }, message) : null,
      error ? e('p', { className: 'notice error', role: 'alert' }, error) : null,
      e(
        'div',
        { className: 'admin-grid clients-grid' },
        e(
          'section',
          { className: 'panel' },
          e(
            'div',
            { className: 'panel-heading' },
            e('h2', null, 'Historique des mouvements'),
            e('span', null, loading ? 'Chargement...' : `${filteredMovements.length} affiché(s)`)
          ),
          e('input', {
            className: 'search-input',
            type: 'search',
            placeholder: 'Rechercher par type, article, client ou fournisseur...',
            value: search,
            onChange: (event) => setSearch(event.target.value),
            'aria-label': 'Rechercher un mouvement',
          }),
          e(
            'div',
            { className: 'table-wrap' },
            e(
              'table',
              null,
              e(
                'thead',
                null,
                e(
                  'tr',
                  null,
                  e('th', null, 'Date'),
                  e('th', null, 'Type'),
                  e('th', null, 'Article'),
                  e('th', null, 'Quantité'),
                  e('th', null, 'Tiers'),
                  canManageStock ? e('th', null, 'Actions') : null
                )
              ),
              e(
                'tbody',
                null,
                filteredMovements.length
                  ? filteredMovements.map((movement) =>
                      e(
                        'tr',
                        { key: movement.id },
                        e('td', null, movement.date_mouvement),
                        e('td', null, e('span', { className: 'role-badge' }, MOVEMENT_TYPES.find(([type]) => type === movement.type)?.[1] || movement.type)),
                        e('td', null, e('strong', null, movement.article_nom), e('span', { className: 'cell-detail' }, movement.article_ref)),
                        e('td', null, movement.quantite),
                        e('td', null, movement.fournisseur_nom || movement.client_nom || '—'),
                        canManageMovement(user, movement.type)
                          ? e(
                              'td',
                              { className: 'actions-cell' },
                              e('button', { className: 'text-button', onClick: () => startEdit(movement) }, 'Modifier'),
                              e('button', { className: 'text-button danger-text', onClick: () => deleteMovement(movement) }, 'Annuler')
                            )
                          : null
                      )
                    )
                  : e('tr', null, e('td', { className: 'empty-state', colSpan: canManageStock ? 6 : 5 }, loading ? 'Chargement des mouvements...' : 'Aucun mouvement enregistré.'))
              )
            )
          )
        ),
        e(
          'section',
          { className: 'panel form-panel' },
          e(
            'div',
            { className: 'panel-heading' },
            e('h2', null, editingId ? 'Modifier le mouvement' : 'Nouveau mouvement'),
            editingId ? e('button', { className: 'text-button', onClick: resetForm }, 'Annuler') : null
          ),
          !canManageStock || articles.length === 0
            ? e('p', { className: 'subtitle' }, canManageStock ? 'Ajoutez d’abord des articles au catalogue.' : 'Aucun droit ne vous permet de créer un mouvement de stock.')
            : e(
                'form',
                { onSubmit: saveMovement },
                e(
                  'label',
                  null,
                  'Opération',
                  e(
                    'select',
                    {
                      name: 'type',
                      value: form.type,
                      onChange: (event) => setForm({
                        ...form,
                        type: event.target.value,
                        id_fournisseur: '',
                        id_client: '',
                      }),
                    },
                    allowedMovementTypes.map(([value, label]) => e('option', { key: value, value }, label))
                  )
                ),
                e(
                  'label',
                  null,
                  'Article',
                  e(
                    'select',
                    {
                      name: 'article_ref',
                      value: form.article_ref || articles[0]?.ref || '',
                      onChange: (event) => setForm({ ...form, article_ref: event.target.value }),
                      required: true,
                    },
                    articles.map((article) =>
                      e(
                        'option',
                        { key: article.ref, value: article.ref },
                        `${article.nom} — ${article.ref} (stock: ${article.v_stocks})`
                      )
                    )
                  )
                ),
                incoming
                  ? suppliers.length
                    ? e(
                        'label',
                        null,
                        'Fournisseur',
                        e(
                          'select',
                          {
                            name: 'id_fournisseur',
                            value: form.id_fournisseur || String(suppliers[0].id),
                            onChange: (event) => setForm({ ...form, id_fournisseur: event.target.value }),
                            required: true,
                          },
                          suppliers.map((supplier) =>
                            e('option', { key: supplier.id, value: supplier.id }, `${supplier.prenom} ${supplier.nom}`)
                          )
                        )
                      )
                    : e(
                        'p',
                        { className: 'notice error' },
                        'Créez un fournisseur pour enregistrer une réception ou un achat.',
                        canManageStock
                          ? e('button', { className: 'text-button', type: 'button', onClick: onSuppliers }, 'Gérer les fournisseurs')
                          : null
                      )
                  : clients.length
                    ? e(
                        'label',
                        null,
                        'Client',
                        e(
                          'select',
                          {
                            name: 'id_client',
                            value: form.id_client || String(clients[0].id),
                            onChange: (event) => setForm({ ...form, id_client: event.target.value }),
                            required: true,
                          },
                          clients.map((client) =>
                            e('option', { key: client.id, value: client.id }, `${client.prenom} ${client.nom}`)
                          )
                        )
                      )
                    : e('p', { className: 'notice error' }, 'Créez d’abord un client pour enregistrer une livraison ou une vente.'),
                e(
                  'div',
                  { className: 'form-row' },
                  e(
                    'label',
                    null,
                    'Quantité',
                    e('input', {
                      name: 'quantite',
                      type: 'number',
                      min: 1,
                      max: incoming ? undefined : Number(articles.find((article) => article.ref === form.article_ref)?.v_stocks || 0) + (editingId ? Number(form.quantite) : 0),
                      value: form.quantite,
                      onChange: (event) => setForm({ ...form, quantite: event.target.value }),
                      required: true,
                    })
                  ),
                  e(
                    'label',
                    null,
                    'Date',
                    e('input', {
                      name: 'date_mouvement',
                      type: 'date',
                      value: form.date_mouvement,
                      onChange: (event) => setForm({ ...form, date_mouvement: event.target.value }),
                      required: true,
                    })
                  )
                ),
                e(
                  'p',
                  { className: 'stock-help' },
                  incoming
                    ? 'Cette opération augmente le stock disponible.'
                    : 'La quantité ne peut pas dépasser le stock disponible.'
                ),
                e(
                  'button',
                  {
                    type: 'submit',
                    className: 'button',
                    disabled: saving || !hasParty,
                  },
                  saving ? 'Enregistrement...' : editingId ? 'Enregistrer les changements' : 'Enregistrer le mouvement'
                )
              )
        )
      )
    )
  );
}

function SuppliersPage({ user, onBack, onStock, onLogout }) {
  const [suppliers, setSuppliers] = useState([]);
  const [form, setForm] = useState({
    nom: '',
    prenom: '',
    tel: '',
    email: '',
    specialite: '',
    ville: '',
  });
  const [editingId, setEditingId] = useState(null);
const [search, setSearch] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  useEffect(() => { setCurrentPage(1); }, [search]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function refreshSuppliers() {
    const data = await api('/suppliers');
    setSuppliers(data);
  }

  useEffect(() => {
    refreshSuppliers().catch((requestError) => setError(requestError.message));
  }, []);

  function resetForm() {
    setEditingId(null);
    setForm({
      nom: '',
      prenom: '',
      tel: '',
      email: '',
      specialite: '',
      ville: '',
    });
  }

  function startEdit(supplier) {
    setEditingId(supplier.id);
    setForm({
      nom: supplier.nom,
      prenom: supplier.prenom,
      tel: supplier.tel,
      email: supplier.email,
      specialite: supplier.specialite || '',
      ville: supplier.ville || '',
    });
    setMessage('');
    setError('');
  }

  async function saveSupplier(event) {
    event.preventDefault();
    setSaving(true);
    setError('');
    setMessage('');
    const formData = new FormData(event.currentTarget);
    const payload = {
      nom: formData.get('nom'),
      prenom: formData.get('prenom'),
      tel: formData.get('tel'),
      email: formData.get('email'),
      specialite: formData.get('specialite'),
      ville: formData.get('ville'),
    };
    try {
      const data = await api(editingId ? `/suppliers/${editingId}` : '/suppliers', {
        method: editingId ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      });
      setMessage(data.message);
      resetForm();
      await refreshSuppliers();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function deleteSupplier(supplier) {
    if (!window.confirm(`Supprimer le fournisseur ${supplier.prenom} ${supplier.nom} ?`)) {
      return;
    }
    setMessage('');
    setError('');
    try {
      const data = await api(`/suppliers/${supplier.id}`, { method: 'DELETE' });
      setMessage(data.message);
      await refreshSuppliers();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  const filtered = suppliers.filter((supplier) =>
    `${supplier.nom} ${supplier.prenom} ${supplier.tel} ${supplier.email} ${supplier.specialite || ''} ${supplier.ville || ''}`.toLowerCase().includes(search.toLowerCase())
  );
  const perPage = parseInt(user && user.lpp ? user.lpp : 10, 10);
  const totalPages = Math.ceil(filtered.length / perPage) || 1;
  const paginatedSuppliers = filtered.slice((currentPage - 1) * perPage, currentPage * perPage);

  return e(
    'main',
    { className: 'dashboard' },
    e(
      'header',
      { className: 'topbar' },
      e('strong', null, 'OKBA INTER'),
      e(
        'div',
        { className: 'topbar-user' },
        e('button', { className: 'button secondary small-button', onClick: onBack }, user.type === 'admin' ? 'Utilisateurs' : 'Accueil'),
        e('button', { className: 'button secondary small-button', onClick: onStock }, 'Stock'),
        e('button', { className: 'button secondary small-button', onClick: onLogout }, 'Déconnexion')
      )
    ),
    e(
      'div',
      { className: 'content' },
      e(
        'div',
        { className: 'page-heading' },
        e(
          'div',
          null,
          e('p', { className: 'eyebrow' }, 'GESTION COMMERCIALE'),
          e('h1', null, 'Fournisseurs'),
          e('p', { className: 'subtitle' }, 'Gérez les fournisseurs utilisés pour les réceptions et les achats.')
        ),
        e('span', { className: 'count-badge' }, `${suppliers.length} fournisseur${suppliers.length === 1 ? '' : 's'}`),
        e('button', { className: 'button secondary small-button', onClick: function () { window.open(API_URL + '/suppliers/export', '_blank'); } }, '\uD83D\uDCE5 Exporter CSV')
      ),
      message ? e('p', { className: 'notice success', role: 'status' }, message) : null,
      error ? e('p', { className: 'notice error', role: 'alert' }, error) : null,
      e(
        'div',
        { className: 'admin-grid clients-grid' },
        e(
          'section',
          { className: 'panel' },
          e(
            'div',
            { className: 'panel-heading' },
            e('h2', null, 'Répertoire'),
            e('span', null, `${filtered.length} affiché(s)`)
          ),
          e('input', {
            className: 'search-input',
            type: 'search',
            placeholder: 'Rechercher un fournisseur...',
            value: search,
            onChange: (event) => setSearch(event.target.value),
            'aria-label': 'Rechercher un fournisseur',
          }),
          e(
            'div',
            { className: 'table-wrap' },
            e(
              'table',
              null,
              e('thead', null, e('tr', null, e('th', null, 'Fournisseur'), e('th', null, 'Téléphone'), e('th', null, 'E-mail'), e('th', null, 'Spécialité'), e('th', null, 'Ville'), e('th', null, 'Actions'))),
              e(
                'tbody',
                null,
                filtered.length
                  ? paginatedSuppliers.map((supplier) =>
                      e(
                        'tr',
                        { key: supplier.id },
                        e('td', null, e('strong', null, `${supplier.prenom} ${supplier.nom}`)),
                        e('td', null, supplier.tel),
                        e('td', null, supplier.email),
                        e('td', null, supplier.specialite || '—'),
                        e('td', null, supplier.ville || '—'),
                        e(
                          'td',
                          { className: 'actions-cell' },
                          e('button', { className: 'text-button', onClick: () => startEdit(supplier) }, 'Modifier'),
                          e('button', { className: 'text-button danger-text', onClick: () => deleteSupplier(supplier) }, 'Supprimer')
                        )
                      )
                    )
                  : e('tr', null, e('td', { className: 'empty-state', colSpan: 6 }, 'Aucun fournisseur enregistré.'))
              )
            ),
            e(Pagination, { page: currentPage, pages: totalPages, total: filtered.length, onPageChange: setCurrentPage })
          )
        ),
        e(
          'section',
          { className: 'panel form-panel' },
          e(
            'div',
            { className: 'panel-heading' },
            e('h2', null, editingId ? 'Modifier le fournisseur' : 'Ajouter un fournisseur'),
            editingId ? e('button', { className: 'text-button', onClick: resetForm }, 'Annuler') : null
          ),
          e(
            'form',
            { onSubmit: saveSupplier },
            e(
              'div',
              { className: 'form-row' },
              e('label', null, 'Prénom', e('input', { name: 'prenom', value: form.prenom, onChange: (event) => setForm({ ...form, prenom: event.target.value }), required: true })),
              e('label', null, 'Nom', e('input', { name: 'nom', value: form.nom, onChange: (event) => setForm({ ...form, nom: event.target.value }), required: true }))
            ),
            e('label', null, 'Téléphone', e('input', { name: 'tel', type: 'tel', value: form.tel, onChange: (event) => setForm({ ...form, tel: event.target.value }), required: true })),
            e('label', null, 'Adresse e-mail', e('input', { name: 'email', type: 'email', value: form.email, onChange: (event) => setForm({ ...form, email: event.target.value }), required: true })),
            e('label', null, 'Spécialité', e('input', { name: 'specialite', value: form.specialite, onChange: (event) => setForm({ ...form, specialite: event.target.value }), maxLength: 100 })),
            e('label', null, 'Ville', e('input', { name: 'ville', value: form.ville, onChange: (event) => setForm({ ...form, ville: event.target.value }), maxLength: 100 })),
            e('button', { type: 'submit', className: 'button', disabled: saving }, saving ? 'Enregistrement...' : editingId ? 'Enregistrer les changements' : 'Créer le fournisseur')
          )
        )
      )
    )
  );
}

const COLUMN_LABELS = {
  id: 'ID',
  model: 'Modèle',
  immatricule: 'Immatriculation',
  annee: 'Année',
  puissance: 'Puissance',
  location: 'En location',
  date_d_loc: 'Début de location',
  date_f_loc: 'Fin de location',
  nom: 'Nom',
  ville: 'Ville',
  adresse: 'Adresse',
  contact: 'Contact',
  d_limite: 'Date limite',
  vehicle_name: 'Véhicule affecté',
  type: 'Type',
  organizer: 'Organisateur',
  start_date: 'Début',
  end_date: 'Fin',
  product_send_deadline: 'Limite d’envoi',
  status: 'Statut',
  allow_late_send: 'Envoi tardif',
  type: 'Type',
  etat: 'État',
  stand_type: 'Stand',
  article_nom: 'Article',
  quantite: 'Quantité',
  date_ch: 'Date',
  agent_nom: 'Agent',
  foire_nom: 'Foire',
  taille_stand: 'Taille du stand',
  logement: 'Logement',
  date_d: 'Début',
  date_f: 'Fin',
  etat: 'État',
  date_c: 'Date de confirmation',
  vendeur_nom: 'Vendeur',
  deco_nom: 'Décorateur',
  chauffeur_nom: 'Chauffeur',
  voiture_nom: 'Véhicule',
  flow: 'État',
  type_user: 'Type utilisateur',
  foire: 'Foire',
  stand: 'Stand',
  liste_stand: 'Liste des stands',
  article: 'Article',
  work: 'Mission',
  fournisseur: 'Fournisseur',
  client: 'Client',
  reservation: 'Réservation',
  empl: 'Employés',
  voiture: 'Véhicule',
  mouvement: 'Mouvement',
  livraison: 'Livraison',
  reception: 'Réception',
  vente: 'Vente',
  achat: 'Achat',
};

const ALL_RESOURCE_LINKS = [
  ['module:employees', 'Employés'],
  ['module:vehicles', 'Véhicules'],
  ['module:fairs', 'Foires'],
  ['module:fair-assignments', 'Équipe des foires'],
  ['module:fair-inventory', 'Stock des foires'],
  ['module:reservations', 'Réservations'],
  ['module:stand-types', 'Types de stands'],
  ['module:stand-inventory', 'Articles des stands'],
  ['module:works', 'Missions'],
  ['module:permissions', 'Droits'],
  ['module:settings', 'Paramètres'],
];

function FairAssignmentsPage({ user, onNavigate, onLogout }) {
  const [fairs, setFairs] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [fairId, setFairId] = useState('');
  const [role, setRole] = useState('vendeur');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function refreshAssignments() {
    const data = await api('/fair-assignments');
    setAssignments(data);
  }

  useEffect(() => {
    Promise.all([api('/fairs'), refreshAssignments()])
      .then(([fairRows]) => {
        setFairs(fairRows);
        if (fairRows.length) {
          setFairId(String(fairRows[0].id));
          setStartDate(fairRows[0].start_date || '');
          setEndDate(fairRows[0].end_date || '');
        }
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  function selectFair(event) {
    const nextId = event.target.value;
    const selectedFair = fairs.find((fair) => String(fair.id) === nextId);
    setFairId(nextId);
    setStartDate(selectedFair?.start_date || '');
    setEndDate(selectedFair?.end_date || '');
    setSuggestions([]);
  }

  async function findSuggestions(event) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    setError('');
    try {
      const data = await api('/fair-assignments/suggestions', {
        method: 'POST',
        body: JSON.stringify({
          fair_id: Number(fairId),
          role,
          start_date: startDate,
          end_date: endDate,
        }),
      });
      setSuggestions(data.suggestions);
      if (!data.suggestions.some((item) => item.available)) {
        setMessage('Aucun membre disponible pour ce rôle et ces dates.');
      }
    } catch (requestError) {
      setError(requestError.message);
      setSuggestions([]);
    } finally {
      setSaving(false);
    }
  }

  async function confirmAssignment(candidate) {
    setSaving(true);
    setMessage('');
    setError('');
    try {
      const response = await api('/fair-assignments', {
        method: 'POST',
        body: JSON.stringify({
          fair_id: Number(fairId),
          user_id: candidate.user_id,
          role,
          start_date: startDate,
          end_date: endDate,
        }),
      });
      setMessage(response.message);
      await refreshAssignments();
      const data = await api('/fair-assignments/suggestions', {
        method: 'POST',
        body: JSON.stringify({
          fair_id: Number(fairId),
          role,
          start_date: startDate,
          end_date: endDate,
        }),
      });
      setSuggestions(data.suggestions);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function removeAssignment(assignment) {
    if (!window.confirm(`Supprimer l’affectation de ${assignment.user_name} ?`)) {
      return;
    }
    setError('');
    setMessage('');
    try {
      const response = await api(`/fair-assignments/${assignment.id}`, {
        method: 'DELETE',
      });
      setMessage(response.message);
      await refreshAssignments();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  const roleLabel = (value) => ROLES.find(([roleValue]) => roleValue === value)?.[1] || value;

  return e(
    'main',
    { className: 'dashboard' },
    e(
      'header',
      { className: 'topbar' },
      e(
        'div',
        null,
        e('strong', null, 'OKBA INTER'),
        e('span', { className: 'topbar-label' }, 'Équipe des foires')
      ),
      e(
        'div',
        { className: 'topbar-user module-nav' },
        e('span', null, `${user.prenom} ${user.nom}`),
        e('button', { className: 'button secondary small-button', onClick: () => onNavigate(user.type === 'admin' ? 'users' : 'home') }, 'Accueil'),
        ...ALL_RESOURCE_LINKS.filter(([key]) => key !== 'module:fair-assignments').map(([key, label]) =>
          e('button', { key, className: 'button secondary small-button', onClick: () => onNavigate(key) }, label)
        ),
        e('button', { className: 'button secondary small-button', onClick: onLogout }, 'Déconnexion')
      )
    ),
    e(
      'div',
      { className: 'content' },
      e(
        'div',
        { className: 'page-heading' },
        e(
          'div',
          null,
          e('p', { className: 'eyebrow' }, 'GESTION OKBA INTER'),
          e('h1', null, 'Équipe des foires'),
          e('p', { className: 'subtitle' }, 'Consultez les disponibilités et confirmez manuellement les propositions de l’équipe.')
        ),
        e('span', { className: 'count-badge' }, `${assignments.length} affectation${assignments.length === 1 ? '' : 's'}`)
      ),
      message ? e('p', { className: 'notice success', role: 'status' }, message) : null,
      error ? e('p', { className: 'notice error', role: 'alert' }, error) : null,
      e(
        'section',
        { className: 'panel form-panel' },
        e('h2', null, 'Proposer une affectation'),
        e('p', { className: 'stock-help' }, 'Les propositions ne créent aucune affectation. Choisissez explicitement un membre disponible pour confirmer l’affectation.'),
        e(
          'form',
          { onSubmit: findSuggestions },
          e(
            'label',
            null,
            'Foire',
            e(
              'select',
              { value: fairId, onChange: selectFair, required: true },
              e('option', { value: '', disabled: true }, fairs.length ? 'Sélectionner...' : 'Aucune foire disponible'),
              fairs.map((fair) => e('option', { key: fair.id, value: fair.id }, fair.nom))
            )
          ),
          e(
            'label',
            null,
            'Rôle recherché',
            e(
              'select',
              { value: role, onChange: (event) => { setRole(event.target.value); setSuggestions([]); } },
              ROLES.filter(([roleValue]) => roleValue !== 'admin').map(([roleValue, label]) =>
                e('option', { key: roleValue, value: roleValue }, label)
              )
            )
          ),
          e(
            'div',
            { className: 'form-row' },
            e('label', null, 'Début', e('input', {
              type: 'date',
              value: startDate,
              onChange: (event) => setStartDate(event.target.value),
              required: true,
            })),
            e('label', null, 'Fin', e('input', {
              type: 'date',
              value: endDate,
              onChange: (event) => setEndDate(event.target.value),
              required: true,
            }))
          ),
          e('button', { className: 'button', type: 'submit', disabled: saving || loading || !fairs.length }, saving ? 'Recherche...' : 'Vérifier les disponibilités')
        )
      ),
      suggestions.length
        ? e(
            'section',
            { className: 'panel' },
            e('h2', null, 'Propositions à examiner'),
            e(
              'div',
              { className: 'table-wrap' },
              e(
                'table',
                null,
                e('thead', null, e('tr', null,
                  e('th', null, 'Membre'),
                  e('th', null, 'Disponibilité'),
                  e('th', null, 'Décision du responsable')
                )),
                e(
                  'tbody',
                  null,
                  suggestions.map((candidate) =>
                    e('tr', { key: candidate.user_id },
                      e('td', null, candidate.user_name),
                      e('td', null, candidate.available ? 'Disponible' : candidate.conflict),
                      e('td', null, candidate.available
                        ? e('button', {
                            className: 'button small-button',
                            type: 'button',
                            disabled: saving,
                            onClick: () => confirmAssignment(candidate),
                          }, 'Confirmer l’affectation')
                        : 'Non proposé')
                    )
                  )
                )
              )
            )
          )
        : null,
      e(
        'section',
        { className: 'panel' },
        e(
          'div',
          { className: 'panel-heading' },
          e('h2', null, 'Affectations confirmées'),
          e('span', null, loading ? 'Chargement...' : `${assignments.length} enregistrée(s)`)
        ),
        e(
          'div',
          { className: 'table-wrap' },
          e(
            'table',
            null,
            e('thead', null, e('tr', null,
              e('th', null, 'Foire'),
              e('th', null, 'Membre'),
              e('th', null, 'Rôle'),
              e('th', null, 'Période'),
              e('th', null, 'Origine'),
              e('th', null, 'Action')
            )),
            e(
              'tbody',
              null,
              assignments.length
                ? assignments.map((assignment) =>
                    e('tr', { key: assignment.id },
                      e('td', null, assignment.fair_name),
                      e('td', null, assignment.user_name),
                      e('td', null, roleLabel(assignment.role)),
                      e('td', null, `${assignment.start_date} – ${assignment.end_date}`),
                      e('td', null, assignment.source === 'manual' ? 'Confirmée manuellement' : assignment.source),
                      e('td', null, e('button', {
                        className: 'text-button danger-text',
                        type: 'button',
                        onClick: () => removeAssignment(assignment),
                      }, 'Supprimer'))
                    )
                  )
                : e('tr', null, e('td', { className: 'empty-state', colSpan: 6 }, loading ? 'Chargement...' : 'Aucune affectation confirmée.'))
            )
          )
        )
      )
    )
  );
}

const FAIR_INVENTORY_TYPES = [
  ['transfer_in', 'Transfert vers la foire'],
  ['transfer_out', 'Retour vers le stock général'],
  ['receipt', 'Réception complémentaire'],
  ['sale', 'Vente'],
  ['return', 'Retour client'],
  ['damage', 'Casse / perte'],
];

function FairInventoryPage({ user, onNavigate, onLogout }) {
  const [fairs, setFairs] = useState([]);
  const [articles, setArticles] = useState([]);
  const [fairId, setFairId] = useState('');
  const [inventory, setInventory] = useState([]);
  const [movements, setMovements] = useState([]);
  const [movementType, setMovementType] = useState('transfer_in');
  const [articleRef, setArticleRef] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [movementDate, setMovementDate] = useState(new Date().toISOString().slice(0, 10));
  const [reference, setReference] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function refreshFairInventory(selectedFairId) {
    if (!selectedFairId) {
      setInventory([]);
      setMovements([]);
      return;
    }
    const data = await api(`/fairs/${selectedFairId}/inventory`);
    setArticles(data.catalog);
    setInventory(data.inventory);
    setMovements(data.movements);
  }

  useEffect(() => {
    api('/fairs')
      .then((fairRows) => {
        setFairs(fairRows);
        if (fairRows.length) {
          setFairId(String(fairRows[0].id));
        }
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refreshFairInventory(fairId).catch((requestError) => setError(requestError.message));
  }, [fairId]);

  async function saveMovement(event) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    setError('');
    try {
      const response = await api(`/fairs/${fairId}/inventory/movements`, {
        method: 'POST',
        body: JSON.stringify({
          movement_type: movementType,
          article_ref: articleRef,
          quantity: Number(quantity),
          movement_date: movementDate,
          reference,
          notes,
        }),
      });
      setMessage(`${response.message} Nouveau stock du stand : ${response.balance}.`);
      setQuantity('1');
      setReference('');
      setNotes('');
      await refreshFairInventory(fairId);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  const movementLabel = (type) =>
    FAIR_INVENTORY_TYPES.find(([value]) => value === type)?.[1] || type;
  const roleLinkFilter = ALL_RESOURCE_LINKS.filter(
    ([key]) => key !== 'module:fair-inventory' && canAccessView(user, key)
  );

  return e(
    'main',
    { className: 'dashboard' },
    e(
      'header',
      { className: 'topbar' },
      e(
        'div',
        null,
        e('strong', null, 'OKBA INTER'),
        e('span', { className: 'topbar-label' }, 'Stock des foires')
      ),
      e(
        'div',
        { className: 'topbar-user module-nav' },
        e('span', null, `${user.prenom} ${user.nom}`),
        e('button', { className: 'button secondary small-button', onClick: () => onNavigate(user.type === 'admin' ? 'users' : 'home') }, 'Accueil'),
        ...roleLinkFilter.map(([key, label]) =>
          e('button', { key, className: 'button secondary small-button', onClick: () => onNavigate(key) }, label)
        ),
        e('button', { className: 'button secondary small-button', onClick: onLogout }, 'Déconnexion')
      )
    ),
    e(
      'div',
      { className: 'content' },
      e(
        'div',
        { className: 'page-heading' },
        e(
          'div',
          null,
          e('p', { className: 'eyebrow' }, 'GESTION OKBA INTER'),
          e('h1', null, 'Stock des foires'),
          e('p', { className: 'subtitle' }, 'Chaque foire dispose de son propre stock. Les mouvements validés sont conservés dans un journal non modifiable.')
        ),
        e('span', { className: 'count-badge' }, `${inventory.length} article${inventory.length === 1 ? '' : 's'}`)
      ),
      message ? e('p', { className: 'notice success', role: 'status' }, message) : null,
      error ? e('p', { className: 'notice error', role: 'alert' }, error) : null,
      e(
        'section',
        { className: 'panel form-panel' },
        e('h2', null, 'Enregistrer un mouvement'),
        e(
          'form',
          { onSubmit: saveMovement },
          e(
            'label',
            null,
            'Foire',
            e(
              'select',
              { value: fairId, onChange: (event) => setFairId(event.target.value), required: true },
              e('option', { value: '', disabled: true }, fairs.length ? 'Sélectionner...' : 'Aucune foire disponible'),
              fairs.map((fair) => e('option', { key: fair.id, value: fair.id }, fair.nom))
            )
          ),
          e(
            'label',
            null,
            'Type de mouvement',
            e(
              'select',
              { value: movementType, onChange: (event) => setMovementType(event.target.value) },
              FAIR_INVENTORY_TYPES.map(([type, label]) => e('option', { key: type, value: type }, label))
            )
          ),
          e(
            'label',
            null,
            'Article',
            e(
              'select',
              { value: articleRef, onChange: (event) => setArticleRef(event.target.value), required: true },
              e('option', { value: '', disabled: true }, 'Sélectionner un article'),
              articles.map((article) => e('option', { key: article.ref, value: article.ref }, `${article.ref} — ${article.nom} (stock général : ${article.v_stocks})`))
            )
          ),
          e(
            'div',
            { className: 'form-row' },
            e('label', null, 'Quantité', e('input', {
              type: 'number',
              min: 1,
              step: 1,
              value: quantity,
              onChange: (event) => setQuantity(event.target.value),
              required: true,
            })),
            e('label', null, 'Date', e('input', {
              type: 'date',
              value: movementDate,
              onChange: (event) => setMovementDate(event.target.value),
              required: true,
            }))
          ),
          e('label', null, 'Référence (facultative)', e('input', {
            value: reference,
            maxLength: 120,
            onChange: (event) => setReference(event.target.value),
          })),
          e('label', null, 'Notes (facultatives)', e('textarea', {
            value: notes,
            maxLength: 500,
            rows: 3,
            onChange: (event) => setNotes(event.target.value),
          })),
          e('button', {
            className: 'button',
            type: 'submit',
            disabled: saving || loading || !fairId || !articles.length,
          }, saving ? 'Enregistrement...' : 'Enregistrer le mouvement')
        )
      ),
      e(
        'section',
        { className: 'panel' },
        e('h2', null, 'Stock actuel du stand'),
        e(
          'div',
          { className: 'table-wrap' },
          e(
            'table',
            null,
            e('thead', null, e('tr', null,
              e('th', null, 'Référence'),
              e('th', null, 'Article'),
              e('th', null, 'Quantité disponible')
            )),
            e(
              'tbody',
              null,
              inventory.length
                ? inventory.map((item) => e('tr', { key: item.article_ref },
                    e('td', null, item.article_ref),
                    e('td', null, item.article_name),
                    e('td', null, item.quantity)
                  ))
                : e('tr', null, e('td', { className: 'empty-state', colSpan: 3 }, loading ? 'Chargement...' : 'Aucun article en stock pour cette foire.'))
            )
          )
        )
      ),
      e(
        'section',
        { className: 'panel' },
        e(
          'div',
          { className: 'panel-heading' },
          e('h2', null, 'Journal des mouvements'),
          e('span', null, 'Les 100 mouvements les plus récents')
        ),
        e(
          'div',
          { className: 'table-wrap' },
          e(
            'table',
            null,
            e('thead', null, e('tr', null,
              e('th', null, 'Date'),
              e('th', null, 'Mouvement'),
              e('th', null, 'Article'),
              e('th', null, 'Variation'),
              e('th', null, 'Référence / notes'),
              e('th', null, 'Enregistré par')
            )),
            e(
              'tbody',
              null,
              movements.length
                ? movements.map((movement) => e('tr', { key: movement.id },
                    e('td', null, movement.movement_date),
                    e('td', null, movementLabel(movement.movement_type)),
                    e('td', null, `${movement.article_ref} — ${movement.article_name}`),
                    e('td', null, movement.quantity_delta > 0 ? `+${movement.quantity_delta}` : movement.quantity_delta),
                    e('td', null, [movement.reference, movement.notes].filter(Boolean).join(' — ')),
                    e('td', null, movement.actor_name)
                  ))
                : e('tr', null, e('td', { className: 'empty-state', colSpan: 6 }, loading ? 'Chargement...' : 'Aucun mouvement enregistré.'))
            )
          )
        )
      ),
    )
  );
}

function SystemSettingsPage({ user, currency, onCurrencyChange, onNavigate, onLogout }) {
  const [formCurrency, setFormCurrency] = useState(currency);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => setFormCurrency(currency), [currency]);

  async function saveSettings(event) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    setError('');
    try {
      const response = await api('/settings', {
        method: 'PUT',
        body: JSON.stringify({ currency: formCurrency.trim().toUpperCase() }),
      });
      setFormCurrency(response.currency);
      onCurrencyChange(response.currency);
      setMessage(response.message);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  return e(
    'main',
    { className: 'dashboard' },
    e(
      'header',
      { className: 'topbar' },
      e(
        'div',
        null,
        e('strong', null, 'OKBA INTER'),
        e('span', { className: 'topbar-label' }, 'Paramètres du système')
      ),
      e(
        'div',
        { className: 'topbar-user module-nav' },
        e('span', null, `${user.prenom} ${user.nom}`),
        e('button', { className: 'button secondary small-button', onClick: () => onNavigate('users') }, 'Accueil'),
        ...ALL_RESOURCE_LINKS.filter(([key]) => key !== 'module:settings').map(([key, label]) =>
          e('button', { key, className: 'button secondary small-button', onClick: () => onNavigate(key) }, label)
        ),
        e('button', { className: 'button secondary small-button', onClick: onLogout }, 'Déconnexion')
      )
    ),
    e(
      'div',
      { className: 'content' },
      e(
        'div',
        { className: 'page-heading' },
        e(
          'div',
          null,
          e('p', { className: 'eyebrow' }, 'GESTION OKBA INTER'),
          e('h1', null, 'Paramètres du système'),
          e('p', { className: 'subtitle' }, 'Définissez la devise utilisée pour afficher les montants de la caisse.')
        )
      ),
      message ? e('p', { className: 'notice success', role: 'status' }, message) : null,
      error ? e('p', { className: 'notice error', role: 'alert' }, error) : null,
      e(
        'section',
        { className: 'panel form-panel' },
        e('h2', null, 'Devise'),
        e(
          'form',
          { onSubmit: saveSettings },
          e(
            'label',
            null,
            'Code devise (ISO 4217)',
            e('input', {
              name: 'currency',
              type: 'text',
              value: formCurrency,
              minLength: 3,
              maxLength: 3,
              pattern: '[A-Za-z]{3}',
              autoCapitalize: 'characters',
              required: true,
              onChange: (event) => setFormCurrency(event.target.value.toUpperCase()),
            })
          ),
          e('p', { className: 'stock-help' }, `Devise actuelle : ${currency}. Exemple : TND, EUR ou USD.`),
          e('button', { className: 'button', type: 'submit', disabled: saving }, saving ? 'Enregistrement...' : 'Enregistrer')
        )
      )
    )
  );
}

function ModulePage({ user, resource, onNavigate, onLogout }) {
  const config = RESOURCE_PAGES[resource];
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState(
    resource === 'fairs' ? { auto_assign: true } : {}
  );
  const [lookupOptions, setLookupOptions] = useState({});
  const [editingId, setEditingId] = useState(null);
const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function refreshRows() {
    const lookupFields = config.fields.filter(([, , type]) => type === 'lookup');
    const [data, options] = await Promise.all([
      api(`/${config.endpoint}`),
      lookupFields.length
        ? api(`/resource-lookups/${resource}`)
        : Promise.resolve({}),
    ]);
    setRows(data);
    setLookupOptions(options);
  }

  useEffect(() => {
    setLoading(true);
    setForm(resource === 'fairs' ? { auto_assign: true } : {});
    refreshRows()
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, [resource]);

  function resetForm() {
    setEditingId(null);
    setForm(resource === 'fairs' ? { auto_assign: true } : {});
  }

  function startEdit(row) {
    setEditingId(row[config.key || 'id']);
    setForm(Object.fromEntries(config.fields.map(([field]) => [field, row[field] ?? ''])));
    setMessage('');
    setError('');
  }

  async function saveRow(event) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    setError('');
    const payload = Object.fromEntries(
      config.fields.map(([field, , type]) => {
        const value = event.currentTarget.elements[field];
        if (type === 'checkbox') {
          return [field, value.checked];
        }
        const submittedValue = value.value;
        return [
          field,
          type === 'lookup' && submittedValue === ''
            ? null
            : type === 'number' ||
          (type === 'lookup' && field.startsWith('id_')) ||
          (type === 'select' && field === 'etat')
            ? Number(submittedValue)
            : submittedValue,
        ];
      })
    );
    try {
      const path = editingId
        ? `/${config.endpoint}/${encodeURIComponent(editingId)}`
        : `/${config.endpoint}`;
      const response = await api(path, {
        method: editingId ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      });
      setMessage(response.message);
      resetForm();
      await refreshRows();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  }

  async function deleteRow(row) {
    const rowKey = row[config.key || 'id'];
    if (!window.confirm(`Supprimer ${config.singular.toLowerCase()} « ${rowKey} » ?`)) {
      return;
    }
    setMessage('');
    setError('');
    try {
      const response = await api(`/${config.endpoint}/${encodeURIComponent(rowKey)}`, {
        method: 'DELETE',
      });
      setMessage(response.message);
      await refreshRows();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function confirmWork(row, role) {
    setMessage('');
    setError('');
    try {
      const response = await api(`/works/${row.id}/confirm`, {
        method: 'POST',
        body: JSON.stringify({ role }),
      });
      setMessage(response.message);
      await refreshRows();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  const filteredRows = rows.filter((row) =>
    config.columns.map((column) => String(row[column] ?? '')).join(' ').toLowerCase().includes(search.toLowerCase())
  );
  const actionsAllowed =
    !config.readOnly &&
    resource !== 'permissions' &&
    hasViewPermission(user, VIEW_PERMISSIONS[`module:${resource}`]);
  const moduleNavigation = ALL_RESOURCE_LINKS.filter(
    ([key]) => key !== `module:${resource}` && canAccessView(user, key)
  );
  const otherNavigation = USER_NAVIGATION.filter(
    ([key]) => !key.startsWith('module:') && canAccessView(user, key)
  );

  return e(
    'main',
    { className: 'dashboard' },
    e(
      'header',
      { className: 'topbar' },
      e(
        'div',
        null,
        e('strong', null, 'OKBA INTER'),
        e('span', { className: 'topbar-label' }, config.title)
      ),
      e(
        'div',
        { className: 'topbar-user module-nav' },
        e('button', { className: 'button secondary small-button', onClick: () => onNavigate(user.type === 'admin' ? 'users' : 'home') }, 'Accueil'),
        ...moduleNavigation.map(([key, label]) =>
          e('button', { key, className: 'button secondary small-button', onClick: () => onNavigate(key) }, label)
        ),
        ...otherNavigation.map(([key, label]) =>
          e('button', { key, className: 'button secondary small-button', onClick: () => onNavigate(key) }, label)
        ),
        e('button', { className: 'button secondary small-button', onClick: onLogout }, 'Déconnexion')
      )
    ),
    e(
      'div',
      { className: 'content' },
      e(
        'div',
        { className: 'page-heading' },
        e(
          'div',
          null,
          e('p', { className: 'eyebrow' }, 'GESTION OKBA INTER'),
          e('h1', null, config.title),
          e('p', { className: 'subtitle' }, `${rows.length} enregistrement${rows.length === 1 ? '' : 's'} dans ce module.`)
        ),
        e('span', { className: 'count-badge' }, `${rows.length} élément${rows.length === 1 ? '' : 's'}`)
      ),
      message ? e('p', { className: 'notice success', role: 'status' }, message) : null,
      error ? e('p', { className: 'notice error', role: 'alert' }, error) : null,
      e(
        'div',
        { className: 'admin-grid clients-grid' },
        e(
          'section',
          { className: 'panel' },
          e(
            'div',
            { className: 'panel-heading' },
            e('h2', null, config.title),
            e('span', null, loading ? 'Chargement...' : `${filteredRows.length} affiché(s)`)
          ),
          e('input', {
            className: 'search-input',
            type: 'search',
            placeholder: `Rechercher : ${config.title.toLowerCase()}...`,
            value: search,
            onChange: (event) => setSearch(event.target.value),
            'aria-label': `Rechercher dans ${config.title}`,
          }),
          e(
            'div',
            { className: 'table-wrap' },
            e(
              'table',
              null,
              e(
                'thead',
                null,
                e(
                  'tr',
                  null,
                  ...config.columns.map((column) => e('th', { key: column }, COLUMN_LABELS[column] || column)),
                  actionsAllowed || resource === 'works' ? e('th', null, 'Actions') : null
                )
              ),
              e(
                'tbody',
                null,
                filteredRows.length
                  ? filteredRows.map((row) =>
                      e(
                        'tr',
                        { key: row[config.key || 'id'] },
                        ...config.columns.map((column) => {
                          const value = row[column];
                          const display = resource === 'permissions' && typeof value === 'boolean'
                            ? (value ? 'Oui' : 'Non')
                            : resource === 'vehicles' && column === 'location' && typeof value === 'boolean'
                            ? (value ? 'Oui' : 'Non')
                            : resource === 'fairs' && column === 'allow_late_send' && typeof value === 'boolean'
                            ? (value ? 'Oui' : 'Non')
                            : resource === 'fairs' && column === 'status'
                            ? (FAIR_STATUSES.find(([status]) => status === value)?.[1] || '')
                            : resource === 'reservations' && column === 'etat'
                            ? (Number(value) ? 'Confirmée' : 'En attente')
                            : value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value);
                          return e('td', { key: column }, display);
                        }),
                        actionsAllowed || resource === 'works'
                          ? e(
                              'td',
                              { className: 'actions-cell' },
                              actionsAllowed
                                ? e(
                                    React.Fragment,
                                    null,
                                    e('button', { className: 'text-button', onClick: () => startEdit(row) }, 'Modifier'),
                                    e('button', { className: 'text-button danger-text', onClick: () => deleteRow(row) }, 'Supprimer')
                                  )
                                : null,
                              resource === 'works' && ['vendeur', 'chauffeur', 'deco'].includes(user.type) && user.id === row[`id_${user.type}`]
                                ? e(
                                    'button',
                                    {
                                      className: 'text-button',
                                      disabled: Boolean(row.confirmations?.[`c_${user.type}`]),
                                      onClick: () => confirmWork(row, user.type),
                                    },
                                    row.confirmations?.[`c_${user.type}`] ? 'Confirmé' : 'Confirmer'
                                  )
                                : null
                            )
                          : null
                      )
                    )
                  : e(
                      'tr',
                      null,
                      e('td', { className: 'empty-state', colSpan: config.columns.length + (actionsAllowed || resource === 'works' ? 1 : 0) }, loading ? 'Chargement...' : 'Aucun enregistrement.')
                    )
              )
            )
          )
        ),
        actionsAllowed
          ? e(
              'section',
              { className: 'panel form-panel' },
              e(
                'div',
                { className: 'panel-heading' },
                e('h2', null, editingId ? `Modifier : ${config.singular.toLowerCase()}` : `Ajouter : ${config.singular.toLowerCase()}`),
                editingId ? e('button', { className: 'text-button', onClick: resetForm }, 'Annuler') : null
              ),
              e(
                'form',
                { onSubmit: saveRow },
                ...config.fields.map(([field, label, type]) =>
                  e(
                    'label',
                    { key: field, className: type === 'checkbox' ? 'permission-checkbox' : undefined },
                    label,
                    type === 'fair-status'
                      ? e(
                          'select',
                          {
                            name: field,
                            value: form[field] ?? '',
                            onChange: (event) => setForm({ ...form, [field]: event.target.value }),
                            required: false,
                          },
                          FAIR_STATUSES.map(([status, statusLabel]) =>
                            e('option', { key: status, value: status }, statusLabel)
                          )
                        )
                      : type === 'textarea'
                      ? e('textarea', {
                          name: field,
                          value: form[field] ?? '',
                          maxLength: 2000,
                          onChange: (event) => setForm({ ...form, [field]: event.target.value }),
                          rows: 3,
                        })
                      : type === 'select' && field === 'flow'
                      ? e(
                          'select',
                          { name: field, value: form[field] ?? 'en attente', onChange: (event) => setForm({ ...form, [field]: event.target.value }), required: !(config.optional || []).includes(field) },
                          ['en attente', 'en cours', 'achevee'].map((value) => e('option', { key: value, value }, value))
                        )
                      : type === 'select' && field === 'type'
                      ? e(
                          'select',
                          {
                            name: field,
                            value: form[field] ?? 'foire',
                            onChange: (event) => setForm({ ...form, [field]: event.target.value }),
                            required: !(config.optional || []).includes(field),
                          },
                          [['foire', 'Foire'], ['marche', 'Marché'], ['WM', 'WM'], ['boutique', 'Boutique']].map(([value, label]) =>
                            e('option', { key: value, value }, label)
                          )
                        )
                      : type === 'select' && field === 'etat'
                      ? e(
                          'select',
                          {
                            name: field,
                            value: form[field] ?? 0,
                            onChange: (event) => setForm({ ...form, [field]: event.target.value }),
                            required: !(config.optional || []).includes(field),
                          },
                          e('option', { value: 0 }, 'En attente'),
                          e('option', { value: 1 }, 'Confirmée')
                        )
                      : type === 'lookup'
                      ? e(
                          'select',
                          {
                            name: field,
                            value: form[field] ?? '',
                            onChange: (event) => setForm({ ...form, [field]: event.target.value }),
                            required: !(config.optional || []).includes(field),
                          },
                          e('option', {
                            value: '',
                            disabled: !(config.optional || []).includes(field),
                          }, (config.optional || []).includes(field) ? 'Aucun véhicule sélectionné' : 'Sélectionner...'),
                          (lookupOptions[field] || []).map((option) =>
                            e('option', { key: option.value, value: option.value }, option.label)
                          )
                        )
                      : type === 'role'
                      ? e(
                          'select',
                          {
                            name: field,
                            value: form[field] ?? '',
                            onChange: (event) => setForm({ ...form, [field]: event.target.value }),
                            required: !(config.optional || []).includes(field),
                            disabled: editingId !== null,
                          },
                          e('option', { value: '', disabled: true }, 'Sélectionner un rôle'),
                          ROLES.map(([role, roleLabel]) => e('option', { key: role, value: role }, roleLabel))
                        )
                      : type === 'checkbox'
                        ? e('input', {
                            name: field,
                            type: 'checkbox',
                            className: 'permission-checkbox-input',
                            checked: Boolean(form[field]),
                            onChange: (event) => setForm({ ...form, [field]: event.target.checked }),
                            disabled: resource === 'fairs' && field === 'auto_assign' && editingId !== null,
                            required: false,
                          })
                        : e('input', {
                            name: field,
                            type,
                            min: type === 'number' ? 0 : undefined,
                            value: form[field] ?? '',
                            onChange: (event) => setForm({ ...form, [field]: event.target.value }),
                            required: !(config.optional || []).includes(field) ||
                              (resource === 'fairs' && field === 'late_send_reason' && form.allow_late_send) ||
                              (resource === 'fairs' && ['start_date', 'end_date'].includes(field) && form.auto_assign),
                          })
                  )
                ),
                resource === 'permissions'
                  ? e('p', { className: 'stock-help' }, 'Ces réglages décrivent les accès historiques par rôle. Les opérations sensibles restent réservées aux administrateurs.')
                  : null,
                resource === 'fairs'
                  ? e('p', { className: 'stock-help' }, 'Par défaut, un vendeur, un chauffeur et un véhicule disponibles sont affectés à la foire. Désactivez l’option pour organiser les affectations manuellement. Le POS sera disponible pour le vendeur pendant les dates de la foire.')
                  : null,
                resource === 'works'
                  ? e('p', { className: 'stock-help' }, 'Une mission créée doit être confirmée par le vendeur, le chauffeur et le décorateur qui lui sont affectés.')
                  : null,
                e('button', { type: 'submit', className: 'button', disabled: saving }, saving ? 'Enregistrement...' : editingId ? 'Enregistrer les changements' : `Créer ${config.singular.toLowerCase()}`)
              )
            )
          : null
      )
    )
  );
}
