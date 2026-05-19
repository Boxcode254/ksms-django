# Automated Database Backups

KSMS runs on Supabase (PostgreSQL). The free tier provides only ~1 day of backup retention, so we maintain an independent off-site backup pipeline using GitHub Actions and Cloudflare R2.

## Architecture

| Layer | Tool | Retention | Purpose |
|-------|------|-----------|---------|
| Supabase auto-backup | Supabase daily snapshot | ~1 day | Emergency parachute |
| App JSON export | `SchoolBackupDownloadView` | On-demand | School portability / compliance |
| Automated pg_dump | GitHub Actions → R2 | 30 days | Real disaster recovery with history |

## GitHub Actions Workflow

**File:** `.github/workflows/supabase-backup.yml`

**Schedule:** Daily at 02:00 UTC (configurable)

**What it does:**
1. Uses the Supabase CLI to run `pg_dump` against the live database
2. Compresses the dump with `gzip`
3. Uploads to Cloudflare R2 (zero egress fees)
4. Deletes backups older than 30 days

## Required Secrets

Configure these in your GitHub repository (`Settings → Secrets and variables → Actions`):

| Secret | How to get it |
|--------|---------------|
| `SUPABASE_DB_PASSWORD` | Supabase Dashboard → Project Settings → Database → Connection string → Password |
| `SUPABASE_PROJECT_REF` | The random string in your Supabase URL: `https://<PROJECT_REF>.supabase.co` |
| `R2_ACCESS_KEY_ID` | Cloudflare Dashboard → R2 → Manage API Tokens → Create API Token |
| `R2_SECRET_ACCESS_KEY` | Generated alongside the API token above |
| `R2_ENDPOINT` | Cloudflare R2 bucket endpoint, e.g. `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `R2_BUCKET` | Name of your R2 bucket (create one in the Cloudflare dashboard) |

## Cost

- **Cloudflare R2:** First 10 GB/month free, then $0.015/GB. A typical KSMS dump is < 50 MB.
- **GitHub Actions:** 2,000 minutes/month free on public repos; 500 on private.
- **Total estimated cost:** $0 for most small-to-medium schools.

## Restoring from an R2 Backup

1. Download the desired `.sql.gz` file from R2:
   ```bash
   aws s3 cp s3://YOUR_BUCKET/YOUR_PROJECT_REF/PROJECT_REF_20260510_020000.sql.gz \
     ./backup.sql.gz --endpoint-url https://YOUR_ACCOUNT.r2.cloudflarestorage.com
   ```

2. Decompress:
   ```bash
   gunzip backup.sql.gz
   ```

3. Restore to a **fresh database** (never overwrite a live one):
   ```bash
   psql "postgresql://postgres:PASSWORD@db.PROJECT_REF.supabase.co:5432/postgres" \
     -f backup.sql
   ```

4. For Supabase-hosted restores, use the **Dashboard** (`Database → Backups → Restore`) or create a **new project** and restore there first.

## Security Notes

- The GitHub Actions workflow only ever reads from the database (`pg_dump`). It never writes.
- R2 API tokens should have **Object Read & Write** permissions scoped to the backup bucket only.
- Never commit database passwords to the repository. Always use GitHub Secrets.
- Rotate `SUPABASE_DB_PASSWORD` and R2 tokens every 90 days.

## Manual Trigger

You can run the workflow anytime from the GitHub Actions tab: **Actions → Supabase Database Backup → Run workflow**.

## Monitoring

The workflow will fail loudly (red) if any step errors. You can enable GitHub notifications for workflow failures, or add a Slack/Discord webhook step if desired.
