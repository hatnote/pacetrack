# PaceTrack Project Log

## Backlog

* Frontend: Home page
  * List of campaigns
  * Campaign progress (backend: provide number of completed goals)
  * Button to file PR
* Pull Request Template
* favicon
* Link to start revision in article list table
* Why do we have two Sun-Times?
* Show goal criteria from metric config
* Link to update.log from the campaign
* "More info" cell for article list
* "This campaign ended ..." banner
* Allow referencing campaigns by unambiguous id prefix
* Archive campaign (no longer shows up in list)

### Deployment

* clear cached data subcommand

### Future

* Data format version
* Data migration tool
* Allow goal renaming by recording the metric + metric args instead of
  the goal name? or maybe just have goal id.


## Complete

* rerender subcommand
  * based off of already-fetched data
* /static/campaign_name/campaign.json
  * Structured version of the data used to generate the campaign info page
* --jsub option for update and update-all subcommands
  * to be used on production, to enable non-overlapping updates on
    campaigns, with parallel updates across campaigns.
* update-all subcommand
* frequency campaign configuration field
   * fetch_frequency
   * save_frequency - Run hourly, keep one per day
   * Allows scaling up to megaprojects (fetch daily) and down to editathon (fetch every 10 minutes)
* Generate campaign.json (cached campaign progress)
* Add goal "desc" field to go with "name"
  * Integrated into campaign overview
  * Also integrated into column tooltip on article list
* Compress full json (.json.gz, you'll need to refetch)
* Rename:
   * "overall_results" -> "goal_results"
   * "specific_results" -> "article_results"
   * Will require refetching
   * To clarify campaign_results are more like overall_results
* campaign_results in state data
* Make has_template metric take multiple templates
* Debug occasional 'parse' keyerror
   * Missing talk page
* update.log in each campaign's `static` folder
* Fix Last Updated date (microseconds)
   * Now just displays normal seconds
