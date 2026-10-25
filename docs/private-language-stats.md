# Private repository language statistics

The chart can include the language totals of selected private repositories owned by `salehghotbani`. Only aggregate byte counts are published. Repository names, URLs, code, and individual repository breakdowns are not saved in the snapshot or chart.

## One-time setup

1. [Create a fine-grained personal access token](https://github.com/settings/personal-access-tokens/new) with `salehghotbani` as the resource owner. Select only the private repositories you want counted, and grant **Metadata: Read-only**. No code-content or write permission is needed.
2. [Add an Actions repository secret](https://github.com/salehghotbani/salehghotbani/settings/secrets/actions/new) named `LANGUAGE_STATS_TOKEN` and paste the token into its secret value. Keep the token out of chat, source files, and command arguments.
3. Run **Refresh language stats** from the repository's Actions page, or wait for its next daily run. Public repositories are included separately with the standard workflow token.

Without the secret, the chart continues to use public repositories. With the secret, it adds only the private repositories that token can access. Forks, repositories owned by other accounts, and the profile repository remain excluded. New private repositories must be added to the token's selected repositories if they should count.

If a private request fails or a previously configured private credential disappears, the workflow preserves the last chart rather than publishing incomplete totals. Renew an expired token and replace the secret when needed.
