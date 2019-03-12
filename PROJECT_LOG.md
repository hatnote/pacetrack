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
* Run hourly, keep one per day
* "More info" cell for article list
* /static/campaign_name/campaign.json
* Generate home page from the campaign.json (cached campaign progress)
* update_frequency campaign configuration field (allows scaling up to megaprojects and down to editathon)
* "This campaign ended ..." banner
* Data format version
* Data migration tool

### Deployment

* Subcommand for running update
  * --jsub flag (issue all jsubs in parallel)
  * --no-parallel?
* update-all subcommand
* update-schedule subcommand
* rerender subcommand
* clear cached data subcommand



## Complete

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
