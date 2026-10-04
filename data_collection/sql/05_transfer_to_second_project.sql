-- Prepared, not executed. Reads the small saved extraction, not the GDELT archive.
CREATE SCHEMA IF NOT EXISTS `forecasting-mentions-second.forecasting_mentions` OPTIONS(location='US');
CREATE TABLE IF NOT EXISTS `forecasting-mentions-second.forecasting_mentions.web_mentions_candidates`
CLUSTER BY domain,person AS
SELECT * FROM `forecasting-mentions-project.forecasting_mentions.web_mentions_candidates`;
CREATE TABLE IF NOT EXISTS `forecasting-mentions-second.forecasting_mentions.web_load_manifest` AS
SELECT * FROM `forecasting-mentions-project.forecasting_mentions.web_load_manifest`;
CREATE TABLE IF NOT EXISTS `forecasting-mentions-second.forecasting_mentions.web_batch_inventory` AS
SELECT * FROM `forecasting-mentions-project.forecasting_mentions.web_batch_inventory`;
