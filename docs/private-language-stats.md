# Private repository language statistics

The chart can include the language totals of all private repositories owned by `salehghotbani`, including private forks. Only aggregate byte counts are published. Repository names, URLs, code, and individual repository breakdowns are not saved in the snapshot or chart.

The collector, aggregation logic, source-line counter, and SVG renderer are custom Python code in `scripts/`. They use only Python's standard library. No chart package or hosted statistics-card service is used. Pagination reads every result page, including accounts with more than 100 repositories.

## Source line counting

The `lines` mode streams the default branch's source archive without extracting or retaining files. It counts **non-empty physical source lines, including comments**, for the source extensions listed in `scripts/source_lines.py`. Notebook code cells are counted under their declared language; markdown cells and execution outputs are excluded. Common dependency/build/vendor directories, minified JS/CSS, declaration files and recognized generated-file headers are excluded. This is a documented source-line measure rather than a complete language parser; unrecognized generated files may still count.

Only aggregate counts are saved. No private source files, repository names, signed URLs or file paths are published. The main card shows eight languages; the expandable card shows every counted language. Both use the same linear scale within their card, and the absolute values are printed alongside the bars.

Line mode needs **Contents: Read-only** in addition to **Metadata: Read-only** on the existing all-repository token. A permission preflight runs before any archive collection. Failed reads preserve the previous statistics instead of publishing a partial result.

To try it, run **Refresh language stats** manually with `metric: lines`. After a successful complete run, set the Actions repository variable `LANGUAGE_STATS_METRIC` to `lines` so daily runs use the same measure. The default is `bytes` until that variable is set; byte mode uses GitHub's languages API and needs Metadata only. The published chart's heading always states its actual unit, and bytes are never relabeled as lines.

## One-time setup

1. [Create a fine-grained personal access token](https://github.com/settings/personal-access-tokens/new) with `salehghotbani` as the resource owner. Under **Repository access**, select **All repositories**, and grant **Metadata: Read-only**. No code-content or write permission is needed. All-repository access also covers future private repositories in this account.
2. [Add an Actions repository secret](https://github.com/salehghotbani/salehghotbani/settings/secrets/actions/new) named `LANGUAGE_STATS_TOKEN` and paste the token into its secret value. Keep the token out of chat, source files, and command arguments.
3. Run **Refresh language stats** from the repository's Actions page, or wait for its next daily run. Public repositories are included separately with the standard workflow token.

Without the secret, the chart continues to use public repositories. With the secret, it adds the private repositories that token can access; to include all of them, the token must use **All repositories**. Public forks, repositories owned by other accounts, and the profile repository remain excluded. Organization-owned repositories are outside the personal-account scope. The daily workflow allows up to 30 minutes to process larger accounts.

If a private request fails or a previously configured private credential disappears, the workflow preserves the last chart rather than publishing incomplete totals. Renew an expired token and replace the secret when needed.
