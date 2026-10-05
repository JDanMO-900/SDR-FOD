
import pandas as pd
from playwright.sync_api import sync_playwright
from io import StringIO
import gspread
from gspread_dataframe import set_with_dataframe
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine,  text


load_dotenv()


# TODO: Datos conexion base de datos
USER = os.getenv('DB_USER')
PASS = os.getenv('DB_PASSWORD')
HOST = os.getenv('DB_HOST')
PORT = os.getenv('DB_PORT')
DB = os.getenv('DB_NAME')

conn = f"mysql+pymysql://{USER}:{PASS}@{HOST}:{PORT}/{DB}"
engine = create_engine(conn)


def extraer_datos():
    # TODO 1: Here a create  a list to get the data
    datos_completos = []
    # TODO 2: I initialize playwright as etl connecting the browser and connectiong to the page
    with sync_playwright() as etl:
        
        browser = etl.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto('https://aviationdb.net/aviationdb/SdrQuery#SUBMIT')
        # TODO 3: I fill the input I want and try to advance
        page.fill("input[name=DATE_OF_REPORT_FROM]", "2025-07-01")
        page.fill("input[name=DATE_OF_REPORT_TO]", "2026-07-01")
        # page.fill("input[name=AIRCRAFT_MANUFACTURER_NAME]", "AIRBUS")
        page.select_option("select[name='NATURE_OF_CONDITION_CODE']", value='F.O.D. (C)')
        page.click("input[type='submit']")
        
        # TODO 4: If the page jump a captcha I solve it and continue before a min pass and wait for the table to load
        input("✅ Resuelve el CAPTCHA y cuando aparezcan los resultados presiona Enter aquí...")
        page.wait_for_selector("css=#maintable", timeout=10000)
        page.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in ["image", "stylesheet", "font", "media"]
            else route.continue_()
            )
        
        # TODO 5: Start the process of webscrapping
        counter = 0
        while True:
            # TODO 6: I get all the content html to explore it with pandas
            html_pagina = page.content()
            # Se utiliza maintable porque la pagina esta compuesta de multiples  tablas y el codigo explotaba si solo tenia table
            tablas = pd.read_html(StringIO(html_pagina), attrs={"id": "maintable"})
            
            # TODO 7: If I found the word I want in the table I get the data, proceed to the conditional
            if tablas:
                
                # TODO 8: Access to the first data I obtain of table and save it in my first array
                df_temp = tablas[0]
                datos_completos.append(df_temp)
                counter += 1
                print(f"Cantidad de filas extraidas: {len(df_temp)}")
                # if counter > 2:
                #     break
                # TODO 9: When the page load I get the Next page button to continue extracting the data and if the condition is tru I can continue
                avanzar = page.locator("input[value='Next Page']")
                if avanzar.count() > 0 and avanzar.is_visible():
                    avanzar.click()
                    page.wait_for_timeout(1000)
                    page.wait_for_selector('css=#maintable')
                    
                else: 
                    # TODO 10: If there is not more data, the while broke and the then I end the procces to treat the data
                    print("Extracción finalizada")
                    break
                
            
                
        
        # TODO: Close connection with the browser
        browser.close()
        
        # TODO 11: Data validation, here the data is verify not to be empty
        if not datos_completos:
            print("No se extrajo ningun dato")
            return pd.DataFrame()
        
        
        df_final = pd.concat(datos_completos, ignore_index=True)
        
        # TODO 12: Data cleaning
        if "Unnamed: 1" in df_final.columns:
            df_final = df_final.drop(columns=['Unnamed: 1'])
        
        return df_final
    
    
# TODO: Fucntion to make the connection and pass the dataframe to be upload to the GS
def cargar_datos_GS(dataframe):
    print("Iniciando cargado de datos a Google Sheets")
    
    credentials = os.getenv('GOOGLE_CREDENTIALS_FILE')
    sheet_id = os.getenv('SPREADSHEET_ID')
    
    
    gc = gspread.service_account(filename=credentials)
    
    gs_load_data = gc.open_by_key(sheet_id)
    sheet_to_load = gs_load_data.sheet1
    
    print("Limpiando y cargando datos nuevos...")
    sheet_to_load.clear()
    set_with_dataframe(sheet_to_load, dataframe)
    
    
# Fill the list with data extracted by the function that got it from the web
dataset_sdr = extraer_datos()


# Validating the data before creating the csv and prepare to load the data into the DB
if not dataset_sdr.empty:
    fact_sdr_reports = dataset_sdr.copy()
 
    fact_sdr_reports.to_csv('sdr_data.csv', index=False)
    print("Datos guardados localmente en sdr_data.csv")
    cargar_datos_GS(fact_sdr_reports)
    print("Datos cargados al google sheets")
    validacion_cvs = input("Ingresa el número de opción para continuar: \n1. Cargar datos a la base de datos\n2. Salir")
    if(validacion_cvs == '1'):
        
        # Getting codes from operators - 3 first characteres
        fact_sdr_reports['operator_code'] = fact_sdr_reports['Operator Control Number'].str[:4]
        # TODO: Creating tables dimensions and fact
        
        # TODO 1: dimension table - operator
        dim_operator = fact_sdr_reports[['operator_code']].drop_duplicates().reset_index(drop=True)
        dim_operator['operator_id'] = dim_operator.index + 1
        dim_operator = dim_operator[['operator_id', 'operator_code']]
        
        # TODO 2: dimension table - aircraft
        dim_aircraft = fact_sdr_reports[['Aircraft Manufacturer', 'Aircraft Group Code']].drop_duplicates().reset_index(drop=True)
        dim_aircraft['aircraft_id'] = dim_aircraft.index + 1
        
        # TODO 3: Dimension table - dates
        report_date = dataset_sdr[['Date Of Report']].rename(columns = {'Date Of Report': 'complete_date'})
        ocurrence_date = dataset_sdr[['Date Of Occurrence']].rename(columns = {'Date Of Occurrence': 'complete_date'})
        
        dim_date = pd.concat([report_date, ocurrence_date], ignore_index=True)
        dim_date.complete_date = pd.to_datetime(dim_date.complete_date, errors='coerce')
        
        dim_date = (
            dim_date
            .dropna(subset=["complete_date"])
            .drop_duplicates(subset=['complete_date'])
            .sort_values('complete_date')
            .reset_index(drop=True)
        )
        
        

        
        
        
        dim_date['date_id'] = dim_date.complete_date.dt.strftime('%Y%m%d').astype(int)
        dim_date['anio'] = dim_date['complete_date'].dt.year
        dim_date['month'] = dim_date['complete_date'].dt.month
        dim_date['day'] = dim_date['complete_date'].dt.day
        dim_date['month_name'] = dim_date['complete_date'].dt.month_name()
        dim_date['day_name'] = dim_date['complete_date'].dt.day_name()
        dim_date['week_of_year'] = dim_date['complete_date'].dt.isocalendar().week.astype('Int64')
        
        
        # Transformar a texto para evitar conflictos con SQL

        dim_date = dim_date[
            [
                'date_id',
                'complete_date',
                'anio',
                'month',
                'month_name',
                'day',
                'day_name',
                'week_of_year'
                ]
            ]
        
        # TODO 3: fact table -sdr reports
        fact_sdr_reports['Date Of Report'] = pd.to_datetime(
            fact_sdr_reports['Date Of Report'],
            errors='coerce'
        )
        
        fact_sdr_reports['Date Of Occurrence'] = pd.to_datetime(
            fact_sdr_reports['Date Of Occurrence'],
            errors='coerce'
        )
        
        # Creating FK for report date
        fact_sdr_reports['report_date_id'] = (
            fact_sdr_reports['Date Of Report'].dt.strftime('%Y%m%d')
            
        )
        
        # Creating FK for occurence date
        fact_sdr_reports['occurrence_date_id'] = (
            fact_sdr_reports['Date Of Occurrence'].dt.strftime('%Y%m%d')
            
        )
        
        
        
        
        
        fact_sdr_reports['report_date_id'] = (
            pd.to_numeric(fact_sdr_reports['report_date_id'], errors='coerce').astype('Int64')
            )
        
        fact_sdr_reports['occurrence_date_id'] = (
            pd.to_numeric(fact_sdr_reports['occurrence_date_id'], errors='coerce').astype('Int64')
            )
        
        
        
        fact_sdr_reports = pd.merge(fact_sdr_reports, dim_operator, on="operator_code", how='left',  validate='many_to_one')
        fact_sdr_reports = pd.merge(fact_sdr_reports, dim_aircraft, on=["Aircraft Manufacturer", "Aircraft Group Code"],  validate='many_to_one')
        
        
        fact_sdr_reports = fact_sdr_reports.drop(
            columns=
            [
                'Aircraft Manufacturer',
                'Aircraft Group Code',
                'operator_code',
                'Operator Control Number',
                'Date Of Report',
                'Date Of Occurrence'
            ],
            errors='ignore'    
        )
        
        
   
        try:
            
            dim_operator['operator_id'] = dim_operator["operator_id"].astype('Int64')
            dim_aircraft['aircraft_id'] = dim_aircraft['aircraft_id'].astype('Int64')
            fact_sdr_reports['operator_id'] = fact_sdr_reports["operator_id"].astype('Int64')
            fact_sdr_reports['aircraft_id'] = fact_sdr_reports["aircraft_id"].astype('Int64')
            date_ids = set(dim_date['date_id'])
            invalid_report_dates = fact_sdr_reports.loc[
                fact_sdr_reports['report_date_id'].notna()
                & ~fact_sdr_reports['report_date_id'].isin(date_ids),
                'report_date_id']
            invalid_occurrence_dates = fact_sdr_reports.loc[
                fact_sdr_reports['occurrence_date_id'].notna()
                & ~fact_sdr_reports['occurrence_date_id'].isin(date_ids),
                'occurrence_date_id'
                ]
            if not invalid_report_dates.empty:
                raise ValueError(
                    'Existen report_date_id que no aparecen en dim_date: '
                    f'{invalid_report_dates.unique().tolist()}'
                    )
                
            if not invalid_occurrence_dates.empty:
                raise ValueError(
                    'Existen occurrence_date_id que no aparecen en dim_date: '
                    f'{invalid_occurrence_dates.unique().tolist()}'
                    )
            
            
            
            
            
            
            with engine.begin() as connection:
                
                connection.execute(text("""
                                        DROP TABLE IF EXISTS fact_sdr_reports
                                                   """))
                
                connection.execute(text("""
                                   DROP TABLE IF EXISTS dim_operator
                                   """))
                
                connection.execute(text("""
                                   DROP TABLE IF EXISTS dim_aircraft
                                   """))
                
                connection.execute(text("""
                                   DROP TABLE IF EXISTS dim_date
                                   """))
                
            
                print("Tablas eliminadas")
                
                # Dimension table operator
                connection.execute(text(
                    """
                    CREATE TABLE dim_operator(
                        operator_id INT NOT NULL,
                        operator_Code VARCHAR(50) NOT NULL,
                        
                        CONSTRAINT pk_dim_operator_code
                            PRIMARY KEY (operator_id),
                        
                        CONSTRAINT  uq_dim_operator_code 
                            UNIQUE (operator_code)
                    ) 
                    ENGINE=InnoDB
                    DEFAULT CHARSET=utf8mb4
                    COLLATE=utf8mb4_unicode_ci
                    """
                ))
                
                # Dimension aicraft
                connection.execute(
                    text(
                        """
                        CREATE TABLE dim_aircraft(
                            aircraft_id INT NOT NULL,
                            `Aircraft Manufacturer` VARCHAR(150),
                            `Aircraft Group Code` VARCHAR(150),
                            
                            CONSTRAINT pk_dim_aircraft
                                PRIMARY KEY (aircraft_id),
                            
                            CONSTRAINT uq_dim_aircraft
                                UNIQUE (`Aircraft Manufacturer`, `Aircraft Group Code`)
                             
                            
                        )
                        ENGINE=InnoDB
                        DEFAULT CHARSET=utf8mb4
                        COLLATE=utf8mb4_unicode_ci
                        """
                    )
                )
                
                

                
                # Dimension dates
                connection.execute(
                    text(
                        """
                        CREATE TABLE dim_date(
                            date_id INT NOT NULL,
                            complete_date date NOT NULL,
                            anio INT,
                            month INT,
                            day INT,
                            month_name VARCHAR(50),
                            day_name VARCHAR(50),
                            week_of_year INT,
                            
                            CONSTRAINT pk_dim_date
                                PRIMARY KEY (date_id),
                            
                            CONSTRAINT uq_dim_date
                                UNIQUE (`complete_date`)
                             
                            
                        )
                        ENGINE=InnoDB
                        DEFAULT CHARSET=utf8mb4
                        COLLATE=utf8mb4_unicode_ci
                        """
                    )
                )
                
                # fact table sdr
                connection.execute(text(
                    """
                    CREATE TABLE fact_sdr_reports(
                        report_id BIGINT NOT NULL AUTO_INCREMENT,
                        operator_id INT NULL,
                        aircraft_id INT NULL,
                        report_date_id INT NULL,
                        occurrence_date_id INT NULL,
                        
                        `Row` INT NULL,
                        `Aircraft Registration` VARCHAR(100) NULL,
                        
                        CONSTRAINT pk_fact_sdr_reports
                            PRIMARY KEY (report_id),
                        
                        CONSTRAINT fk_fact_operator
                            FOREIGN KEY (operator_id)
                            REFERENCES dim_operator(operator_id)
                            ON UPDATE CASCADE
                            ON DELETE RESTRICT,
                            
                        CONSTRAINT fk_fact_aircraft
                            FOREIGN KEY (aircraft_id)
                            REFERENCES dim_aircraft(aircraft_id)
                            ON UPDATE CASCADE
                            ON DELETE RESTRICT,
                            
                        CONSTRAINT fk_fact_report_date
                            FOREIGN KEY (report_date_id)
                            REFERENCES dim_date(date_id)
                            ON UPDATE CASCADE
                            ON DELETE RESTRICT,
                        
                        CONSTRAINT fk_fact_occurrence_date
                            FOREIGN KEY (occurrence_date_id)
                            REFERENCES dim_date(date_id)
                            ON UPDATE CASCADE
                            ON DELETE RESTRICT
                    ) 
                    ENGINE=InnoDB
                    DEFAULT CHARSET=utf8mb4
                    COLLATE=utf8mb4_unicode_ci
                    """
                ))
                
                
                
                
                # Cargar tablas
                dim_operator.to_sql(
                    name='dim_operator',
                    con=engine,
                    if_exists='append',
                    index=False
                    )
                
                print("Dimensión de operadores cargada correctamente.")
                dim_aircraft.to_sql(
                    name='dim_aircraft',
                    con=engine,
                    if_exists='append',
                    index=False
                )
                
                
                dim_date.to_sql(
                    name='dim_date',
                    con=engine,
                    if_exists='append',
                    index=False
                )
                
                print("Dimensión de FECHAS  cargada correctamente.")
                
                # 5. Cargar después la tabla de hechos
                fact_sdr_reports.to_sql(
                    name='fact_sdr_reports',
                    con=engine,
                    if_exists='append',
                    index=False
                    )
                print("Datos subidos en el esquema SDR-Reports")
        except Exception as e:
            print(f"Ha succedido un error al conectar o subir los datos: {e}")
        finally:
            engine.dispose()

