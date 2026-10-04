# pennylane-mcp-claude

Votre comptabilité Pennylane, interrogée en français depuis Claude.

Vous installez ce serveur vous-même, avec votre propre jeton Pennylane. Aucun intermédiaire ne s'ajoute entre Claude, votre machine et Pennylane.

---

## 1. Ce que c'est

Pennylane a une API complète, mais elle ne se parle qu'en requêtes HTTP : pagination par curseur, filtres en JSON, un jeton par dossier. Ce serveur la traduit en **87 outils MCP** que Claude appelle tout seul. Vous demandez « quelles factures clients sont en retard ? », et Claude interroge Pennylane, trie et répond.

Les outils couvrent la balance, les écritures, le lettrage, les journaux, les clients, les fournisseurs, les factures, les devis, les produits, les abonnements et les exports FEC. Ils lisent et ils **écrivent** : Claude peut créer une facture ou marquer un paiement.

Ce dépôt est un fork de [melvynx/pennylane-mcp-server](https://github.com/melvynx/pennylane-mcp-server) (MIT, Melvyn Morice), qui a écrit les outils métier. Le fork ajoute trois choses :

| Ajout | Ce que ça change pour vous |
|---|---|
| OAuth embarqué et transport HTTP (`src/pennylane_mcp/oauth.py`, `server.py`) | Le serveur se branche sur claude.ai web et mobile, protégé par un mot de passe |
| Factures lisibles (`tools/customer_invoices.py`, `tools/quotes.py`) | « Impayées », « en retard avant le 15 », « émises en septembre » s'obtiennent en un appel. Le filtre `status`, que l'API refuse, est appliqué par le serveur. Les listes sont compactes, et la fiche facture contient ses lignes, ses paiements et ses rapprochements bancaires |
| Déploiement (`Dockerfile`, `compose.yaml`, `deploy/Caddyfile`) | Un serveur public avec HTTPS automatique, en une commande |

Pennylane propose aussi son propre connecteur MCP ; celui-ci s'en distingue par ses outils d'écriture et par le travail sur les factures, et le choix entre les deux dépend de votre usage.

La documentation amont (référence outil par outil, notions comptables) se trouve dans [`docs/`](docs/).

---

## 2. Comment ça marche

Deux façons de l'utiliser, selon l'endroit où vous parlez à Claude.

```
EN LOCAL (Claude Desktop, Claude Code)
  Claude ──stdio──▶ pennylane-mcp-server (sur votre ordinateur) ──HTTPS──▶ API Pennylane

SUR UN SERVEUR (claude.ai web et mobile)
  claude.ai ──HTTPS──▶ Caddy (certificat auto) ──▶ conteneur pennylane-mcp ──HTTPS──▶ API Pennylane
                                                   │ OAuth embarqué : mot de passe à la connexion
                                                   └ volume /state : jetons de connexion conservés
```

**En local**, Claude Desktop lance le serveur lui-même et lui parle par l'entrée et la sortie standard. Rien n'est exposé sur Internet. C'est la voie la plus simple, mais elle ne marche que sur l'ordinateur où le serveur est installé.

**Sur un serveur**, claude.ai doit joindre votre serveur depuis Internet, en HTTPS. Le serveur embarque son propre serveur d'autorisation OAuth. La première fois que vous branchez le connecteur, claude.ai ouvre une page qui vous demande votre mot de passe. claude.ai reçoit ensuite des jetons de connexion, que le serveur conserve sur disque : un redémarrage ne vous déconnecte pas.

---

## 3. Comment l'utiliser

### Prérequis : un jeton Pennylane

Dans Pennylane : **Paramètres → Connectivité → Développeurs**, puis créez un *Company API Token*. Cochez au minimum ces droits :

`ledger_accounts:all`, `journals:all`, `ledger_entries:all`, `trial_balance:readonly`, `fiscal_years:readonly`, `customers:all`, `customer_invoices:all`, `supplier_invoices:all`

Fournisseurs, produits, devis, catégories, abonnements et exports ont leurs propres droits dans la même page : cochez ceux des outils que vous comptez utiliser. Un outil qui répond `403` signale un droit manquant sur le jeton.

Ce jeton donne accès à toute la comptabilité du dossier. Traitez-le comme un mot de passe : jamais dans un mail, jamais dans un dépôt git.

### Voie A : en local, avec Claude Desktop

1. Ouvrez un terminal. Sur macOS : ⌘ + Espace, tapez « Terminal », Entrée. Sur Windows : menu Démarrer, « PowerShell ».
2. Installez [uv](https://docs.astral.sh/uv/getting-started/installation/), qui télécharge et lance le serveur pour vous.
   - macOS ou Linux : `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows : `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
3. **Fermez le terminal et ouvrez-en un nouveau**, sinon la commande `uvx` reste introuvable. Testez ensuite le téléchargement du serveur :

   ```bash
   uvx --from git+https://github.com/Matthieusabourin2/pennylane-mcp-claude python -c "import pennylane_mcp; print('ok')"
   ```

   `ok` doit s'afficher. Sur un Mac qui n'a jamais servi au développement, macOS propose d'abord d'installer les « outils de ligne de commande » (git en fait partie) : acceptez, puis relancez la commande.
4. Trouvez le chemin complet de `uvx` : `which uvx` sur macOS (souvent `/Users/VOTRENOM/.local/bin/uvx`), `where uvx` sur Windows. Claude Desktop ne connaît pas votre `PATH`, d'où le chemin complet.
5. Dans Claude Desktop : **Paramètres → Développeur → Modifier la configuration**. Le Finder (ou l'Explorateur) montre le fichier `claude_desktop_config.json` : ouvrez-le avec un éditeur de texte brut. Avec TextEdit, passez d'abord par **Format → Convertir au format texte**, sinon les guillemets deviennent typographiques et le fichier ne se lit plus. Si le fichier est vide ou contient `{}`, remplacez tout par le bloc ci-dessous. S'il contient déjà d'autres réglages, ajoutez seulement l'entrée `"pennylane"` dans `"mcpServers"` (ou la clé `"mcpServers"` entière si elle manque), en gardant une virgule entre deux entrées.

   ```json
   {
     "mcpServers": {
       "pennylane": {
         "command": "/chemin/complet/vers/uvx",
         "args": ["--from", "git+https://github.com/Matthieusabourin2/pennylane-mcp-claude", "pennylane-mcp-server"],
         "env": { "PENNYLANE_API_TOKEN": "votre-jeton-pennylane" }
       }
     }
   }
   ```

6. Quittez complètement Claude Desktop (⌘ + Q sur macOS), puis relancez-le. Demandez : « Liste mes factures clients en retard. »

Avec **Claude Code**, une seule commande suffit (`-s user` rend le serveur disponible dans tous vos projets) :

```bash
claude mcp add -s user pennylane -e PENNYLANE_API_TOKEN=votre-jeton -- uvx --from git+https://github.com/Matthieusabourin2/pennylane-mcp-claude pennylane-mcp-server
```

### Voie B : sur un serveur, pour claude.ai web et mobile

Il vous faut une machine joignable depuis Internet (un VPS, une VM chez Scaleway, OVH ou ailleurs, ou un serveur chez vous) et un nom de domaine. Le guide pas à pas est dans **[`docs/deploiement-serveur.md`](docs/deploiement-serveur.md)**. En résumé :

```bash
git clone https://github.com/Matthieusabourin2/pennylane-mcp-claude.git
cd pennylane-mcp-claude
cp .env.example .env        # puis remplir : jeton Pennylane, domaine, mot de passe
docker compose up -d --build
```

Puis, dans claude.ai : **Paramètres → Connecteurs → Ajouter un connecteur personnalisé**. Les connecteurs personnalisés dépendent de votre offre Claude ; sur une offre Team ou Enterprise, c'est un propriétaire de l'organisation qui les ajoute.

1. URL : `https://votre-domaine/mcp`
2. Dans les paramètres avancés, choisissez **« Utiliser votre propre client OAuth »**. L'identifiant client est libre (par exemple `claude-pennylane`), et le secret client reste **vide**. Les deux autres choix échouent : ce serveur n'accepte pas l'enregistrement automatique des clients.
3. Une page « pennylane-mcp » s'ouvre : saisissez la valeur de `MCP_BEARER_TOKEN` (ou de `MCP_OAUTH_PASSWORD`, si vous l'avez définie).

Le connecteur apparaît ensuite aussi dans l'application mobile Claude.

### Sécurité, à lire avant d'exposer le serveur

- **Le mot de passe est la seule barrière** entre Internet et votre comptabilité, en écriture. Générez-le avec `openssl rand -base64 32` et ne le réutilisez nulle part. Le serveur ne limite pas les tentatives : un mot de passe court se devine.
- **Changer le mot de passe ne déconnecte pas** les sessions déjà ouvertes : leurs jetons de rafraîchissement restent valides. En cas de fuite, changez-le dans `.env`, puis effacez les jetons et redémarrez : `docker compose down`, `docker volume rm pennylane-mcp-claude_oauth-state` (le préfixe est le nom du dossier), `docker compose up -d`. Rebranchez ensuite le connecteur dans claude.ai.
- Le serveur refuse de démarrer si l'OAuth est activé sans mot de passe ou sans adresse publique HTTPS. Il refuse aussi de renvoyer un code d'autorisation ailleurs que vers claude.ai.
- `.env` et `dossiers.json` sont exclus du dépôt git et de l'image Docker. Gardez-les ainsi.

### Limites connues

- Au-delà d'environ 58 factures en mode compact, la réponse dépasse la taille qu'un outil peut renvoyer et elle est tronquée. Les compteurs (`count`, `is_complete`) restent en tête. Resserrez alors la période ou filtrez par client.
- `pennylane_get_quote` et les outils d'écriture renvoient encore `public_file_url`. Chaque lecture de ce champ régénère le lien public du PDF et invalide le précédent.
- Plusieurs dossiers Pennylane sur un même serveur : c'est possible avec un fichier `dossiers.json` (voir [`docs/deploiement-serveur.md`](docs/deploiement-serveur.md)). Toute personne qui connaît le mot de passe accède alors à **tous** les dossiers.

### Développer

```bash
pip install -e .
python -m unittest discover -s tests     # tests des fonctions pures, sans jeton
```

---

## Licence

MIT. La licence d'origine de Melvyn Morice est conservée dans [`LICENSE`](LICENSE).
