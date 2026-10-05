CREATE VIEW manufacturer_fod_quantity AS
SELECT
CASE
WHEN `Aircraft Manufacturer` IS NOT NULL THEN `Aircraft Manufacturer` ELSE 'UNSPECIFIED'
END `Aircraft Manufacturer`
,
COUNT(*) `Quantity of reports`
FROM fact_sdr_reports report
LEFT JOIN dim_aircraft da ON da.aircraft_id = report.aircraft_id
GROUP BY `Aircraft Manufacturer`
ORDER BY `Aircraft Manufacturer`;


CREATE VIEW operator_fod_count AS
SELECT
operator_Code,
count(*) `Quantity`
FROM fact_sdr_reports report
LEFT JOIN  dim_operator op ON op.operator_id = report.operator_id
GROUP BY operator_Code
HAVING `Quantity` > 1
order by operator_Code
;



CREATE VIEW incidencias_year AS
WITH eventos_unificados AS (
    -- Bloque 1: Extraemos solo las ocurrencias
    SELECT
        occurrence.anio AS anio,
        occurrence.month AS mes,
        1 AS es_ocurrencia,
        0 AS es_reporte
    FROM fact_sdr_reports sdr
    INNER JOIN sdr.dim_date occurrence ON occurrence.date_id = sdr.occurrence_date_id

    UNION ALL

    -- Bloque 2: Extraemos solo los reportes
    SELECT
        report.anio AS anio,
        report.month AS mes,
        0 AS es_ocurrencia,
        1 AS es_reporte
    FROM fact_sdr_reports sdr
    INNER JOIN sdr.dim_date report ON report.date_id = sdr.report_date_id
)
SELECT
    CONCAT(anio, '-', mes) AS anio_mes,
    SUM(es_ocurrencia) AS total_ocurrencias,
    SUM(es_reporte) AS total_reportes
FROM eventos_unificados
GROUP BY
    anio,
    mes
ORDER BY
    anio,
    mes;

;


