# Déployer le serveur pour claude.ai

Ce guide donne les grandes lignes. Comptez une demi-heure si c'est votre première fois. Il suppose une machine Linux joignable depuis Internet et un nom de domaine. L'hébergeur est votre choix : un VPS, une VM chez Scaleway, OVH, Hetzner, ou un serveur chez vous derrière une box.

## Ce qu'il faut avant de commencer

| Élément | Pourquoi |
|---|---|
| Une machine Linux avec 1 Go de RAM | le conteneur est léger ; la plus petite offre d'un hébergeur suffit |
| Un accès SSH à cette machine | pour taper les commandes ci-dessous ; sans compte `root`, préfixez-les par `sudo` |
| Un nom de domaine ou un sous-domaine | claude.ai n'accepte qu'une adresse HTTPS, et le certificat HTTPS exige un nom |
| Les ports 80 et 443 ouverts | Caddy en a besoin pour obtenir le certificat et pour répondre |
| Un jeton Pennylane | voir « Prérequis » dans le [README](../README.md) |

## Étape 1 : pointer le domaine vers la machine

Chez le gestionnaire de votre domaine, créez un enregistrement **A** (adresse IPv4) ou **AAAA** (IPv6). Exemple : `pennylane.mondomaine.fr` vers l'adresse IP publique de la machine.

Vérifiez depuis votre ordinateur : `ping pennylane.mondomaine.fr` doit répondre avec cette adresse. La propagation prend de quelques minutes à quelques heures.

## Étape 2 : installer Docker

Sur la machine, suivez la [documentation officielle de Docker](https://docs.docker.com/engine/install/) pour votre distribution. Sur Debian ou Ubuntu, le script officiel fait tout :

```bash
curl -fsSL https://get.docker.com | sh
```

Vérifiez : `docker compose version` doit afficher une version.

## Étape 3 : récupérer le code et le configurer

```bash
apt update && apt install -y git        # git manque souvent sur une image minimale
git clone https://github.com/Matthieusabourin2/pennylane-mcp-claude.git
cd pennylane-mcp-claude
cp .env.example .env
chmod 600 .env
openssl rand -base64 32     # copiez le résultat : ce sera votre mot de passe
nano .env
```

Dans `.env`, remplissez quatre lignes :

| Variable | Valeur |
|---|---|
| `PENNYLANE_API_TOKEN` | votre jeton Pennylane |
| `MCP_DOMAIN` | `pennylane.mondomaine.fr` (sans `https://`) |
| `MCP_PUBLIC_URL` | `https://pennylane.mondomaine.fr` (sans slash final) |
| `MCP_BEARER_TOKEN` | le mot de passe généré juste avant |

## Étape 4 : démarrer

```bash
docker compose up -d --build
```

La première fois, la construction prend une à deux minutes. Caddy obtient ensuite le certificat HTTPS tout seul, auprès de Let's Encrypt.

Vérifiez depuis votre ordinateur :

```bash
curl https://pennylane.mondomaine.fr/.well-known/oauth-protected-resource
```

Une réponse JSON qui contient votre adresse prouve que le domaine, le certificat et le serveur répondent. Elle ne prouve pas que le jeton Pennylane est bon : le premier appel d'outil depuis Claude le dira. En cas d'échec, regardez les journaux :

```bash
docker compose logs caddy          # certificat, domaine, ports
docker compose logs pennylane-mcp  # configuration, jeton Pennylane
```

| Symptôme | Cause probable |
|---|---|
| Caddy n'obtient pas de certificat | le domaine ne pointe pas encore vers la machine, ou les ports 80 et 443 sont fermés (pare-feu de l'hébergeur ou de la machine) |
| `MCP_PUBLIC_URL doit être l'adresse publique HTTPS…` | la ligne est vide, ou ne commence pas par `https://` |
| `MCP_OAUTH_ENABLED=1 exige MCP_BEARER_TOKEN` | le mot de passe manque dans `.env` |
| Les outils répondent `401` ou `403` côté Pennylane | jeton Pennylane invalide, ou droits manquants sur le jeton |

## Étape 5 : brancher claude.ai

Suivez la section « Voie B » du [README](../README.md). L'URL du connecteur est `https://pennylane.mondomaine.fr/mcp`. N'oubliez pas le `/mcp` final.

Pour Claude Code sur un autre ordinateur, le mot de passe sert aussi de jeton :

```bash
claude mcp add --transport http pennylane https://pennylane.mondomaine.fr/mcp --header "Authorization: Bearer VOTRE_MCP_BEARER_TOKEN"
```

## Mettre à jour

```bash
cd pennylane-mcp-claude
git pull
docker compose up -d --build
```

Les jetons de connexion sont gardés dans le volume `oauth-state` : la mise à jour ne déconnecte pas claude.ai. N'utilisez pas `docker compose down -v` : il efface ce volume (il faut alors rebrancher le connecteur) et aussi les certificats de Caddy, que Let's Encrypt ne délivre qu'un nombre limité de fois par semaine.

## Autres façons d'héberger

Le fichier `compose.yaml` n'est qu'un exemple. Le serveur est un conteneur ordinaire, qui demande quatre choses où qu'il tourne :

1. les variables d'environnement de `.env`, plus celles fixées dans `compose.yaml` (`MCP_TRANSPORT=streamable-http`, `MCP_HOST=0.0.0.0`, `MCP_OAUTH_ENABLED=1`, `MCP_OAUTH_STATE=/state/oauth.json`) ;
2. un disque persistant monté sur `/state`, sans lequel chaque redémarrage déconnecte claude.ai ;
3. une adresse HTTPS publique qui renvoie vers le port 8000 du conteneur, et dont la valeur figure dans `MCP_PUBLIC_URL` ;
4. une seule instance à la fois, parce que les jetons vivent en mémoire et dans un fichier local.

Quelques pistes, sans les détailler ici :

- **Un reverse proxy existant** (Nginx, Traefik) : supprimez le service `caddy` de `compose.yaml`, publiez le port 8000 en local et faites pointer le proxy dessus.
- **Sans nom de domaine** : [Tailscale Funnel](https://tailscale.com/kb/1223/funnel) donne une adresse HTTPS publique en `*.ts.net` à une machine, même derrière une box.
- **Une plateforme qui déploie des conteneurs** depuis GitHub, avec un `Dockerfile` : renseignez les variables dans son interface, ajoutez un disque persistant sur `/state`, et prenez l'adresse qu'elle fournit pour `MCP_PUBLIC_URL`.

## Plusieurs dossiers Pennylane

Remplacez `PENNYLANE_API_TOKEN` par un fichier `dossiers.json` (format dans [`amont-README.md`](amont-README.md)), créé **avant** le démarrage : s'il manque, Docker crée un dossier vide à sa place. Montez-le dans le conteneur, en écriture, parce que le serveur y enregistre le dossier actif. Dans le service `pennylane-mcp` de `compose.yaml` :

```yaml
    volumes:
      - oauth-state:/state
      - ./dossiers.json:/app/dossiers.json
```

et `PENNYLANE_CONFIG_PATH=/app/dossiers.json` dans `.env`. Le mot de passe ouvre alors tous les dossiers à la fois.
