# Overview
Script aimed at scraping SHiFT Codes from websites, currently all provided from the great work done at  
https://mentalmars.com  
https://www.polygon.com  
https://www.ign.com  
https://xsmashx88x.github.io/Shift-Codes  

##### Current webpages scraped include:

- [Borderlands](https://mentalmars.com/game-news/borderlands-golden-keys/)
- [Borderlands 2](https://mentalmars.com/game-news/borderlands-2-golden-keys/)
- [Borderlands 3](https://mentalmars.com/game-news/borderlands-3-golden-keys/)
- Borderlands 4  

  > [mentalmars](https://mentalmars.com/game-news/borderlands-4-shift-codes/) |  [polygon](https://www.polygon.com/borderlands-4-active-shift-codes-redeem/) | [ign](https://www.ign.com/wikis/borderlands-4/Borderlands_4_SHiFT_Codes) | [xsmashx88x](https://xsmashx88x.github.io/Shift-Codes/)
- [Borderlands The Pre-Sequel](https://mentalmars.com/game-news/bltps-golden-keys/)
- [Tiny Tina's Wonderlands](https://mentalmars.com/game-news/tiny-tinas-wonderlands-shift-codes)

Instead of publishing this as part of [Fabbi's autoshift](https://github.com/Fabbi/autoshift), this is aimed at publishing a machine readable file that can be hit by autoshift.  This reduces the load on mentalmars as it's likely not ok to have swarms of autoshifts scraping their website.  Instead codes are published to the repo here: 
- [autoshift-codes](https://github.com/zarmstrong/autoshift-codes)

  > With a direct link [here](https://raw.githubusercontent.com/zarmstrong/autoshift-codes/refs/heads/main/shiftcodes.json)

## Intent

This script has been setup with the intent that other webpages could be scraped. The Python Dictionary `webpages` can be used to customise the webpage, the tables and their contents. This may need adjusting as mentalmars' website updates over time.

TODO List: 
- [x] Scrape mentalmars
- [x] output into a autoshift compatible json file format
- [ ] change to find `table` tags in `figure` tags to reduce noise in webpage
- [x] publish to GitHub [here](https://raw.githubusercontent.com/ugoogalizer/autoshift-codes/main/shiftcodes.json)
- [x] dockerise and schedule
- [x] identify expired codes on website (strikethrough)
- [x] Identify expired codes by date (via `mark_expired.py`)
  > `mark_expired.py` sets `expired: true` when an entry’s `expires` time is in the past (supports ISO and common date formats).


# Use
## Command Line Use
``` bash
# If only generating locally
python ./autoshift_scraper.py 

# If pushing to GitHub:
python ./autoshift_scraper.py --user GITHUB_USERNAME --repo GITHUB_REPOSITORY_NAME --token GITHUB_AUTHTOKEN

# If scheduling: 
python ./autoshift_scraper.py --schedule 5 # redeem every 5 hours
```

## Docker Use

The following docker environment variables are in use: 

| Environment Variable | Use |
| -------------------- | --- |
| GITHUB_USER | The username that owns the GitHub repo to commit to | 
| GITHUB_REPO | The name of the GitHub repository to commit to
| GITHUB_TOKEN | The GitHub fine-grained personal access token -- see below for more details | 
| PARSER_ARGS | (Optional) Additional parameters to pass in, like "--schedule 2 --verbose" |

Example: 
``` bash
docker run -d -t -i \
-e GITHUB_USER='ugoogalizer' \ 
-e GITHUB_REPO='autoshift-codes' \
-e GITHUB_TOKEN='github_pat_***' \
-e PARSER_ARGS='--verbose --schedule 2' \
-v autoshift:/autoshift/data \
--name autoshift-scraper \
zacharmstrong/autoshift-scraper:latest
```
Example localhost build image: 
``` bash
docker run -d -t -i \
-e GITHUB_USER='zacharmstrong' \
-e GITHUB_REPO='autoshift-codes' \
-e GITHUB_TOKEN='github_pat_***' \
-e PARSER_ARGS='--verbose --schedule 2' \
-v autoshift:/autoshift/data \
--name autoshift-scraper \
localhost/autoshift-scraper:latest

```

## Kubernetes Use

Example Deployment file

``` yaml

--- # deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  labels:
    app: autoshift-scraper
  name: autoshift-scraper
#  namespace: autoshift
spec:
  selector:
    matchLabels:
      app: autoshift-scraper
  revisionHistoryLimit: 0
  template:
    metadata:
      labels:
        app: autoshift-scraper
    spec:
      containers:
        - name: autoshift-scraper
          image: zacharmstrong/autoshift-scraper:latest
          imagePullPolicy: IfNotPresent
          env:
            - name: GITHUB_USER
              value: "zarmstrong"
            - name: GITHUB_REPO
              value: "autoshift-codes"
            - name: GITHUB_TOKEN
              valueFrom:
                secretKeyRef:
                  name: autoshift-scraper-secret
                  key: githubtoken
            - name: PARSER_ARGS
              value: "--schedule 2"
          resources:
            requests:
              cpu: 100m
              memory: 100Mi
            limits:
              cpu: "100m"
              memory: "500Mi"
          volumeMounts:
            - mountPath: /autoshift-scraper/data
              name: autoshift-scraper-pv
      volumes:
        - name: autoshift-scraper-pv
          # If this is NFS backed, you may have to add the nolock mount option to the storage class
          persistentVolumeClaim:
            claimName: autoshift-scraper-pvc
---
apiVersion: v1
kind: PersistentVolumeClaim
# If this is NFS backed, you may have to add the nolock mount option to the storage class
metadata:
  name: autoshift-scraper-pvc
#  namespace: autoshift
spec:
  storageClassName: managed-nfs-storage-retain
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 10Mi


# kubectl create namespace autoshift
# kubectl config set-context --current --namespace=autoshift
# kubectl create secret generic autoshift-scraper-secret --from-literal=githubtoken='XXX' 

# To get the username and password use: 
# kubectl get secret autoshift-scraper-secret -o jsonpath="{.data.githubtoken}" | base64 -d

```

# Configuring GitHub connectivity

You can authenticate with **either** a fine‑grained personal access token (recommended) **or** a classic PAT.

**Fine‑grained PAT (recommended)**

* Grant access only to the destination repository.
* Permissions: **Contents → Read and write**.
* Example token format: `github_pat_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX` (starts with `github_pat_`).

**Classic PAT**

* Scope: **repo**.
* Example token format: `ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX` (starts with `ghp_`).

Use either token with:

```bash
python mark_expired.py --user <OWNER> --repo <REPO> --token <PAT>
```


# Setting up development environment

## Minimum requirements

* **Python 3.11+** (recommended)
* **pip**

> `mark_expired.py` uses the standard library’s `zoneinfo` for Central Time handling and the GitHub uploader relies on `PyGithub` (installed via `requirements.txt`).

## Original setup

```bash
# create and activate a virtual environment
python3.11 -m venv .venv
source ./.venv/bin/activate

# install all dependencies
pip install -r requirements.txt
```

## Docker Container Image Build

``` bash

# Once off setup: 
git clone TODO

# Personal parameters
export HARBORURL=harbor.test.com

git pull

#Set Build Parameters
export VERSIONTAG=0.7

#Build the Image
docker build -t autoshift-scraper:latest -t autoshift-scraper:${VERSIONTAG} . 

#Get the image name, it will be something like 41d81c9c2d99: 
export IMAGE=$(docker images -q autoshift-scraper:latest)
echo ${IMAGE}

#Tag and Push the image into local harbor
docker login ${HARBORURL}:443
docker tag ${IMAGE} ${HARBORURL}:443/autoshift/autoshift-scraper:latest
docker tag ${IMAGE} ${HARBORURL}:443/autoshift/autoshift-scraper:${VERSIONTAG}
docker push ${HARBORURL}:443/autoshift/autoshift-scraper:latest
docker push ${HARBORURL}:443/autoshift/autoshift-scraper:${VERSIONTAG}

#Tag and Push the image to public docker hub repo
docker login -u ugoogalizer docker.io/ugoogalizer/autoshift-scraper
docker tag ${IMAGE} docker.io/ugoogalizer/autoshift-scraper:latest
docker tag ${IMAGE} docker.io/ugoogalizer/autoshift-scraper:${VERSIONTAG}
docker push docker.io/ugoogalizer/autoshift-scraper:latest
docker push docker.io/ugoogalizer/autoshift-scraper:${VERSIONTAG}

```

# Testing

Unit tests are provided for the main parser logic, including the MentalMars and Polygon Borderlands 4 scrapers.

## Running the tests

1. Install test dependencies (pytest):
   ```bash
   pip install pytest
   ```

2. Run all tests from the project root:
   ```bash
   pytest
   ```

3. To run a specific test file:
   ```bash
   pytest tests/test_parsers.py
   ```

## What is tested

- Extraction and normalization of codes from sample HTML for both MentalMars and Polygon BL4 sources.
- Handling of invalid or duplicate codes.
- Error handling for missing or malformed HTML.

Test files are located in the `tests/` directory.

## Mark codes as expired (local helper)

`mark_expired.py` helps you keep `data/shiftcodes.json` accurate by:

1. **Bulk sweep mode** (no positional codes):

   * Compares each entry’s `expires` time to a reference moment.
   * If `expires` is earlier than the reference, sets `expired: true`.
   * Does **not** modify `expires` values in bulk mode.

2. **Targeted mode** (one or more codes provided):

   * If `--expires ISO` **is provided**: *only* overwrites the `expires` field for the targeted codes (does **not** touch `expired`).
   * If `--expires` **is omitted**: sets `expires` to **now** (interpreted in **America/Chicago** then converted to UTC) **and** sets `expired: true` for the targeted codes.

3. **Dry‑run** reporting (`--dry-run`):

   * Prints an easy‑to‑read audit of what would change, including per‑code decisions and a summary block.

### Timezone behavior (important)

* All ambiguous or naive inputs (no `Z`/offset) are interpreted in **America/Chicago** (Central time, honoring DST: CST UTC−06:00 / CDT UTC−05:00). They are then **converted to UTC** for storage/comparison.
* Display strings include Central local time with the correct UTC offset, e.g. `Oct 12, 2025, 02:00 PM UTC-05:00`.

### Supported `expires` formats (for reading)

* ISO 8601: `2025-09-20T00:00:00Z`, `2025-09-20 00:00:00+00:00`, `2025-09-20T00:00:00-05:00`
* Date‑only ISO: `2025-09-28` (interpreted as midnight **America/Chicago**, then to UTC)
* Named‑month: `Sep 15, 2025`, `September 15, 2025`, `Sep 15, 2025 12:00 AM`
* Slash formats: `09/01/2025` (US), `28/09/2025` (EU) — heuristic: if first number > 12 ⇒ day/month/year
* Month/day only: `Sep 01`, `January 05` — year derived from `archived` (preferred) or the reference time
* Special cases: `Unknown`, empty string ⇒ skipped in bulk mode

> When writing/replacing `expires` (targeted mode), the script writes **ISO UTC** timestamps.

---

### Usage

#### Bulk sweep (no codes):

```bash
# Compare against now (America/Chicago -> UTC)
python mark_expired.py --dry-run

# Compare against a specific reference time (supports offset or naive)
python mark_expired.py --expires "2025-10-01T00:00:00Z" --dry-run
python mark_expired.py --expires "2025-10-01 00:00:00" --dry-run   # interpreted in America/Chicago

# Apply changes
python mark_expired.py
python mark_expired.py --expires "2025-10-01T00:00:00Z"
```

#### Targeted mode (one or more codes, comma‑separated):

```bash
# Overwrite only the 'expires' field for two codes (no change to 'expired')
python mark_expired.py "CODE1, CODE2" --expires "2025-10-12 14:00:00"

# Set both 'expires' (to now) and 'expired'=true for the codes
python mark_expired.py "CODE1, CODE2"

# Preview first
python mark_expired.py "CODE1, CODE2" --dry-run
```

#### Input file location

* By default: `data/shiftcodes.json`.
* Override via CLI: `--file path/to/whatever.json`.
* Or export an environment variable:

```bash
export SHIFTCODESJSONPATH=/absolute/or/relative/path/shiftcodes.json
python mark_expired.py  # will use the env value by default
```

If the file is missing, you’ll get a hint to run `autoshift_scraper.py` first.

---

### GitHub upload (optional)

If you pass credentials and a repo, the script can update (or bootstrap) the file on GitHub **only when changes were made and not in dry‑run**.

```bash
python mark_expired.py --user <OWNER> --repo <REPO> --token <PAT>
```

* **Token types:**

  * **Fine‑grained PAT:** grant **Contents: Read and write** to the target repository (and include it in the resource list).
  * **Classic PAT:** scope **repo**.
* **Branch:** uses the repository **default branch** (fallback: `main`).
* **Destination path:** the **basename** of your local file (e.g. `shiftcodes.json`) is used in the repo root.
* **Empty repository:** the script can bootstrap an initial commit with your file.
* **Console output:** prints whether the file was Created/Updated/Bootstrapped and echoes the exact filename it worked on.

Examples:

```bash
# Update default file when changes occur
python mark_expired.py --user you --repo codes --token <PAT>

# Update a specific file in a different repo
python mark_expired.py --file data/sample_shiftcodes_full.json \
  --user you --repo test-repo --token <PAT>
```

> **Note:** Upload is skipped on `--dry-run`.
