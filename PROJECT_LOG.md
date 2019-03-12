# PaceTrack Project Log

## Backlog

* Make has_template metric take multiple templates
* Home page
  * List of campaigns
  * Button to file PR
* Pull Request Template
* favicon
* Link to start revision in article list table
* Why do we have two Sun-Times?
* Add metric "desc" field to go with "name"
* Show goal criteria from metric config
* Link to update.log from the campaign
* Compress full json
* Run hourly, keep one per day
* "More info" cell for article list
* /static/campaign_name/campaign.json
* Generate home page from the campaign.json (cached campaign progress)
* update_frequency campaign configuration field (allows scaling up to megaprojects and down to editathon)
* "This campaign ended ..." banner

### Deployment

* Subcommand for running update
  * --jsub flag (issue all jsubs in parallel)
  * --no-parallel?
* update-all subcommand
* update-schedule subcommand
* rerender subcommand



## Complete

* Debug occasional 'parse' keyerror
   * Missing talk page
* update.log in each campaign's `static` folder
* Fix Last Updated date (microseconds)
   * Now just displays normal seconds
