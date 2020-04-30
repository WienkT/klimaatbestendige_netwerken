"""
Class to manage the start of a BIVAS run

Jurjen de Jong, 23-2-2018
"""

import os
from pathlib import Path
import shutil
import subprocess
import time
import sqlite3
import pandas as pd
import requests
import xml.dom.minidom
import logging
from datetime import datetime
from klimaatbestendige_netwerken.pyBIVAS import pyBIVAS

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class BIVAS_runner():
    # API settings
    bivasurl = 'http://127.0.0.1'
    outputsettingsfile = Path(__file__).parent / 'input/pyBIVAS_runner_OutputParameters.xml'

    def __init__(self, scenarioName: str, scenarioID: int, BIVAS_installation_dir, BIVAS_database_file=None):
        """

        :param scenarioID:
        """

        self.scenarioName = scenarioName
        self.scenarioID = scenarioID
        self.BIVAS_installation_dir = Path(BIVAS_installation_dir)

        assert (self.BIVAS_installation_dir / 'BIVAS.exe').exists(), 'BIVAS installation not found'

        self.BIVAS_database = self.BIVAS_installation_dir / 'Bivas.db'

        # Check if new BIVAS_database_file exists and copy to BIVAS folder
        if BIVAS_database_file:
            BIVAS_database_file = Path(BIVAS_database_file)
            assert BIVAS_database_file.exists(), 'BIVAS database not found'

            logger.info('Copying databasefile to run folder')
            shutil.copyfile(BIVAS_database_file, self.BIVAS_installation_dir / 'Bivas.db')
        assert self.BIVAS_database.exists(), 'BIVAS database not found'

    def prepare_database(self, waterscenario=None, trafficScenario=None):
        """
        This function copys the reference databasefile to the rundir
        It updates the database with the new waterscenario
        and apply the correct scenario name in this database

        waterscenario - Path to waterscenario csv - file

        TODO: Update this to work through API

        """

        # Validate input
        if waterscenario:
            waterscenario = Path(waterscenario)
            assert waterscenario.exists(), 'Waterscenario file not found'

        BIVAS = pyBIVAS(self.BIVAS_database)
        df_trafficscenarios = BIVAS.trafficscenario_numberoftrips()


        # Do changes to database:
        con = sqlite3.connect(self.BIVAS_database)
        c = con.cursor()

        # Update waterscenario with given file
        if waterscenario:
            # Delete current water_scenario_values
            sql = "DELETE FROM water_scenario_values WHERE 1"
            c.execute(sql)

            sql = "DELETE FROM water_scenarios WHERE 1"
            c.execute(sql)

            # Write waterdata to database

            # Read waterscenario file
            df = pd.read_csv(waterscenario, header=0, index_col=None)
            df = df[['ArcID', 'SeasonID', 'WaterLevel__m', 'RateOfFlow__m3_s', 'WaterSpeed__m_s', 'WaterDepth__m']]
            df['WaterScenarioID'] = 1

            # Add new water_scenario
            df.to_sql('water_scenario_values', con,
                      if_exists='append', index=False)

            # Rename water_scenario
            # waterscenario_name = waterscenario.stem
            # sql = """UPDATE water_scenarios SET Description = "{}" WHERE ID = {}""".format(
                # waterscenario_name, waterscenario)
            # c.execute(sql)


            waterscenario_id = 1
            waterscenario_name = 'TEST waterscenario'
            waterscenario_type = 1
            sql = """INSERT into water_scenarios VALUES ({}, '{}', {})""".format(
                        waterscenario_id,
                        waterscenario_name,
                        waterscenario_type
                    )
            c.execute(sql)

            # Remove water scenario. I'm simply updating all scenarios
            # Otherwise I should check the BranchSet structure
            sql = """UPDATE parameters SET WaterScenarioID = 1 WHERE 1"""
            c.execute(sql)

        else:
            # Remove water scenario. I'm simply updating all scenarios
            # Otherwise I should check the BranchSet structure
            sql = """UPDATE parameters SET WaterScenarioID = NULL WHERE 1"""
            c.execute(sql)

        # Set scenario name and description
        date_string = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        description = f'Date: {date_string}, Waterscenario: {waterscenario}, TrafficScenario: {trafficScenario},'

        sql = """
        UPDATE scenarios
        SET Name = "{}",
            Description = "{}"
        WHERE ID = {}
        """.format(
            self.scenarioName, description, self.scenarioID)
        c.execute(sql)

        # Update traffic Scenario. I'm simply updating all scenarios
        # Otherwise I should check the BranchSet structure
        if trafficScenario:
            if isinstance(trafficScenario, int):
                sql = """UPDATE parameters SET TrafficScenarioID = "{}" WHERE 1""".format(trafficScenario)
                c.execute(sql)
            else:
                trafficScenarioID = df_trafficscenarios.index[df_trafficscenarios['Description'] == trafficScenario][0]
                sql = """UPDATE parameters SET TrafficScenarioID = "{}" WHERE 1""".format(trafficScenarioID)
                c.execute(sql)

        con.commit()
        con.close()

        logger.info('BIVAS database copied and updated')

    def run(self):
        # Open BIVAS
        executable = self.BIVAS_installation_dir / 'BIVAS.exe'

        subprocess.Popen(str(executable))
        time.sleep(10)

        # Start simulation through the webapi
        url = self.bivasurl + '/Scenarios/' + str(self.scenarioID) + '/Calculate'
        headers = {'Content-Type': 'application/xml; charset=UTF-8'}
        with open(self.outputsettingsfile, 'rb') as data:
            requests.post(url, data=data, headers=headers, verify=False)

        logger.info('BIVAS simulation started')
        time.sleep(5)

    def await_simulation(self):
        """
        Wait until the simulation is finished
        Then close BIVAS and continue
        """
        # Test if overall statistics can be requested

        url = self.bivasurl + '/Scenarios/' + str(self.scenarioID) + '/Output/OverallStatistics'
        data = None
        headers = {'Accept': 'application/xml'}
        d = None
        while not d:
            try:
                d = requests.get(url, data=data, headers=headers, verify=False)
            except ConnectionError as error:
                logger.warning(f'Failed to connect: {error}')

            logger.info('{}: Waiting for BIVAS to finish...'.format(datetime.now()))
            time.sleep(60)

        logger.info(xml_to_string(d.text))

        logger.info('{}: Finished!'.format(datetime.now()))

        # Close BIVAS
        logger.info('Closing BIVAS')
        os.system('taskkill /f /im Bivas.exe')
        time.sleep(5)


# class BIVAS_API:
#
#     post_headers = {'Content-Type': 'application/xml; charset=UTF-8'}
#     get_headers = {'Accept': 'application/xml'}
#
#     def __init__(self):
#         self.bivas_url='http://127.0.0.1'
#
#     def post_calculation(self, scenario_id, xmlfile_outputsettings):
#         url = self.bivasurl + '/Scenarios/' + str(scenario_id) + '/Calculate'
#         with open(outputsettingsfile, 'rb') as data:
#             requests.post(url, data=data, headers=post_headers, verify=False)
#
#     def get_output_overallstatistics(self, scenario_id):
#         url = self.bivasurl + '/Scenarios/' + str(scenario_id) + '/Output/OverallStatistics'
#         d = requests.get(url, data=None, headers=self.get_headers, verify=False)
#         return d

def xml_to_string(xmlstring):
    xmldom = xml.dom.minidom.parseString(xmlstring)
    pretty_xml_as_string = xmldom.toprettyxml()


if __name__ == '__main__':
    p = BIVAS_runner(
        scenarioName = 'run_id_0',
        scenarioID = 49,
        BIVAS_installation_dir=Path(r'D:\Software\BIVAS'),
        BIVAS_database_file=Path(r'D:\Path\to\BIVAS.db')
    )
    p.prepare_database(
        waterscenario = Path(r'D:\path\to\Waterscenario_Q1000.csv'),
        trafficScenarioID= 11
    )

    p.run()
    p.await_simulation()
