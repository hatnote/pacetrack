
## URL structure

```
tools.wmflabs.org/pacetrack/  -> home page listing of all wikiprojects + last updated
tools.wmflabs.org/pacetrack/project-slug/index.html -> metadata + high-level progress table + link to article list
tools.wmflabs.org/pacetrack/project-slug/articles.html  -> table of articles and metrics and possibly call-to-action links
```

Probably all generated pages should have prominent last updated.

## Process

1. Load config
1. Load article list
1. Load articles (page ids, maybe cur revids)
1. Load other article attributes, based on current campaign goals
    * Can generate the article list table here (or later)
1. Compute campaign-wide stats and projections
1. Produce campaign page and update home page, etc.
