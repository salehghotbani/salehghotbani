# Private repository language statistics

The chart can include the language totals of all private repositories owned by `salehghotbani`, including private forks. Only aggregate byte counts are published. Repository names, URLs, code, and individual repository breakdowns are not saved in the snapshot or chart.

The collector, aggregation logic, and SVG renderer are custom Python code in `scripts/update-language-stats.py`. They use only Python's standard library. GitHub's languages API supplies byte counts; no chart package or hosted statistics-card service is used. Pagination reads every result page, including accounts with more than 100 repositories.

## One-time setup

1. [Create a fine-grained personal access token](https://github.com/settings/personal-access-tokens/new) with `salehghotbani` as the resource owner. Under **Repository access**, select **All repositories**, and grant **Metadata: Read-only**. No code-content or write permission is needed. All-repository access also covers future private repositories in this account.
2. [Add an Actions repository secret](https://github.com/salehghotbani/salehghotbani/settings/secrets/actions/new) named `LANGUAGE_STATS_TOKEN` and paste the token into its secret value. Keep the token out of chat, source files, and command arguments.
3. Run **Refresh language stats** from the repository's Actions page, or wait for its next daily run. Public repositories are included separately with the standard workflow token.

Without the secret, the chart continues to use public repositories. With the secret, it adds the private repositories that token can access; to include all of them, the token must use **All repositories**. Public forks, repositories owned by other accounts, and the profile repository remain excluded. Organization-owned repositories are outside the personal-account scope. The daily workflow allows up to 30 minutes to process larger accounts.

If a private request fails or a previously configured private credential disappears, the workflow preserves the last chart rather than publishing incomplete totals. Renew an expired token and replace the secret when needed.
