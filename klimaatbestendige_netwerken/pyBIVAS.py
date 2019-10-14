# -*- coding: utf-8 -*-
"""
Created on Sat Aug 26 14:01:43 2017

@author: jong_jn
"""
import pandas as pd
import networkx as nx
import geopandas
from shapely.geometry import Point, LineString
import sqlite3
import numpy as np


class pyBIVAS():
    """
    This class helps in postprocessing BIVAS data
    """

    NSTR_shortnames = {
        -2: 'Onbekend',
        -1: 'Leeg (geen lading)',
        0: '0 - Landbouw',
        1: '1 - Voeding en vee',
        2: '2 - Mineralen',
        3: '3 - Aardolie',
        4: '4 - Ertsen',
        5: '5 - Staal',
        6: '6 - Bouwmaterialen',
        7: '7 - Meststoffen',
        8: '8 - Chemische prod.',
        9: '9 - Goederen'
    }

    def __init__(self, databasefile=None):
        """
        Initialise class
        """
        if databasefile:
            self.connectToSQLiteDatabase(databasefile)

    def connectToMySQLDatabase(self, host='localhost', user='root', password='', db='bivas'):
        """
        Connect to MySQL database
        By default connects to localhost
        """

        import pymysql.cursors
        import pymysql

        self.connection = pymysql.connect(host=host,
                                          user=user,
                                          password=password,
                                          db=db,
                                          charset='utf8mb4',
                                          cursorclass=pymysql.cursors.DictCursor)

        return self.connection

    def connectToSQLiteDatabase(self, databasefile):
        """
        Connect to sqlite3 databasefile (.db)
        """
        print('Loading database: {}'.format(databasefile))
        self.databasefile = databasefile
        self.connection = sqlite3.connect(self.databasefile)
        return self.connection

    def set_scenario(self, scenario):
        """
        Set scenario to perform analysis
        An int will be assumed to be the id
        A string will be assumed to be the name
        """

        scenarioOverview = self.sqlOverviewOfScenarios()

        if isinstance(scenario, int):
            self.scenarioID = scenario
            self.scenarioName = scenarioOverview.loc[self.scenarioID, 'Name']
        elif isinstance(scenario, str):
            self.scenarioName = scenario
            self.scenarioID = scenarioOverview[scenarioOverview['Name'] == self.scenarioName].index[0]

        self.trafficScenario = scenarioOverview.loc[self.scenarioID,
                                                    'TrafficScenarioID']
        self.WaterScenarioID = scenarioOverview.loc[self.scenarioID,
                                                    'WaterScenarioID']

    def sqlOverviewOfScenarios(self):
        """Overview of all scenarios with parameters"""

        sql = """
        SELECT *
        FROM scenarios
        JOIN branching$branch_sets ON scenarios.ID = branching$branch_sets.BranchID
        JOIN parameters ON branching$branch_sets.ID = parameters.BranchSetID
        ORDER BY scenarios.ID
        """
        df = pd.read_sql(sql, self.connection)
        df = df.set_index('ID')
        return df

    def sqlCountTripsPerTrafficScenario(self):
        """Count trips per traffic scenario"""
        sql = """
        SELECT traffic_scenarios.Description, count(*)
        FROM trips
        LEFT JOIN traffic_scenarios ON TrafficScenarioID = traffic_scenarios.ID
        GROUP BY TrafficScenarioID"""
        df = pd.read_sql(sql, self.connection)
        return df

    def sqlCountTripsInTrafficScenario(self):
        """Trips in trafficScenario per date"""

        sql = """
        SELECT DATE(trips.DateTime) AS date,
               COUNT(*) AS nTrips,
               AVG(TotalWeight__t) as AvgTotalWeight__t,
               AVG(NumberOfTrips) as AvgNumberOfTrips
        FROM trips
        LEFT JOIN traffic_scenarios ON TrafficScenarioID = traffic_scenarios.ID
        WHERE traffic_scenarios.ID = '{0}'
        GROUP BY DATE(trips.DateTime)
        """.format(self.trafficScenario)
        df = pd.read_sql(sql, self.connection)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        return df

    def sqlCountTrips(self):
        """Trips in scenario per date"""

        sql = """
        SELECT DATE(DateTime) AS date,
               count(*) AS nTrips,
               AVG(TotalWeight__t) as AvgTotalWeight__t,
               SUM(TotalWeight__t * NumberOfTrips) as SumTotalWeight__t,
               SUM(NumberOfTrips) as SumNumberOfTrips
        FROM trips_{0}
        GROUP BY DATE(DateTime)
        """.format(self.scenarioID)
        df = pd.read_sql(sql, self.connection)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        return df

    def sqlInfeasibleTrips(self):
        """Infeasible Trips in scenario per date"""
        sql = """
        SELECT DATE(trips_{0}.DateTime) AS date,
               count(*) AS nTrips,
               SUM(trips_{0}.TotalWeight__t) AS SumTotalWeight__t
        FROM infeasible_trips
        LEFT JOIN trips_{0} ON infeasible_trips.TripID = trips_{0}.ID
        LEFT JOIN branching$branch_sets ON infeasible_trips.BranchSetID = branching$branch_sets.Id
        WHERE branching$branch_sets.BranchID = {0}
        GROUP BY DATE(DateTime)
        """.format(self.scenarioID)
        df = pd.read_sql(sql, self.connection)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        return df

    def loadAllInfeasible(self):
        sql = """
        SELECT nstr_types.Code AS "NSTR",
               appearance_types.Description AS "Vorm",
               DATE(trips.DateTime) AS "Days",
               trips.ID AS "ID",
               (trips.NumberOfTrips) AS "Aantal Vaarbewegingen (-)",
               (trips.TotalWeight__t * trips.NumberOfTrips) AS "Totale Vracht (ton)",
               (trips.TwentyFeetEquivalentUnits * trips.NumberOfTrips) AS "Totale TEU (-)"
        FROM infeasible_trips
        LEFT JOIN trips_{0} AS trips ON infeasible_trips.TripID = trips.ID
        LEFT JOIN nstr_types ON trips.NstrTypeCode = nstr_types.Code
        LEFT JOIN branching$branch_sets ON infeasible_trips.BranchSetID = branching$branch_sets.Id
        LEFT JOIN appearance_types ON trips.AppearanceTypeID = appearance_types.ID
        WHERE branching$branch_sets.BranchID = {0}
        """.format(self.scenarioID)

        df = pd.read_sql(sql, self.connection)
        df['Days'] = pd.to_datetime(df['Days'])
        df = df.replace({'NSTR': self.NSTR_shortnames})
        df = df.set_index('ID')
        return df

    def sqlRouteStatistics(self):
        """Routes in scenario per date"""

        sql = """
        SELECT DATE(trips_{0}.DateTime) AS date,
               SUM( VariableCosts__Eur) AS SumVariableCosts,
               SUM( FixedCosts__Eur) AS SumFixedCosts,
               SUM( TravelTime__min) AS SumTravelTime,
               SUM( Distance__km  ) AS SumDistance,
               SUM( VariableCosts__Eur * trips_{0}.NumberOfTrips) AS SumVariableCostsTrips,
               SUM( FixedCosts__Eur * trips_{0}.NumberOfTrips   ) AS SumFixedCostsTrips,
               SUM( FixedCosts__Eur * trips_{0}.NumberOfTrips  +  VariableCosts__Eur * trips_{0}.NumberOfTrips) AS SumTotalCostsTrips,
               SUM( TravelTime__min * trips_{0}.NumberOfTrips   ) AS SumTravelTimeTrips,
               SUM( Distance__km * trips_{0}.NumberOfTrips      ) AS SumDistanceTrips,
               SUM( trips_{0}.NumberOfTrips                     ) AS SumNumberOfTrips,
               COUNT(*) AS count
        FROM route_statistics_{0}
        LEFT JOIN trips_{0} ON route_statistics_{0}.TripID = trips_{0}.ID
        GROUP BY DATE(trips_{0}.DateTime)
        """.format(self.scenarioID)
        df = pd.read_sql(sql, self.connection)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        return df

    def sqlRouteStatisticsFromRoutes(self):
        """
        Routes in scenario per date
        Use this if route_statistics does not exist
        No other statistics but the count
        """

        sql = """
        SELECT DATE(trips_{0}.DateTime) AS date,
               COUNT(*) AS count
        FROM routes_{0}
        LEFT JOIN trips_{0} ON routes_{0}.TripID = trips_{0}.ID
        WHERE RouteIndex=0
        GROUP BY DATE(trips_{0}.DateTime)
        """.format(self.scenarioID)
        df = pd.read_sql(sql, self.connection)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        return df

    def sqlArcsPerWaterScenario(self):
        """Count number of Arcs in each water scenario"""

        sql = """
        SELECT ID,Description,COUNT(*) AS nArcs
        FROM water_scenario_values
        LEFT JOIN water_scenarios ON water_scenario_values.WaterScenarioID = water_scenarios.ID
        WHERE SeasonID=1
        GROUP BY ID
        """
        return pd.read_sql(sql, self.connection)

    def sqlWaterDepthForArcIDs(self, ArcIDs):
        """
        For a list of ArcIDs get the waterdepth
        """

        ArcIDsStr = str(ArcIDs).strip('[]')
        sql = """
        SELECT SeasonID, WaterDepth__m, ArcID
        FROM water_scenario_values
        WHERE ArcID IN ({}) AND WaterScenarioID={}
        """.format(ArcIDsStr, self.WaterScenarioID)
        df = pd.read_sql(sql, self.connection)
        df = df.set_index('SeasonID')

        gp = df.groupby('ArcID')
        ndf = pd.DataFrame()
        for name, group in gp:
            ndf[name] = group['WaterDepth__m']
        return ndf

    def sqlRoutesForArcIDs(self, ArcIDs):
        """
        For a list of ArcIDs give the number of daily routes
        """

        ArcIDsStr = str(ArcIDs).strip('[]')
        sql = """
        SELECT DATE(trips_{0}.DateTime) AS date,
               COUNT(trips_{0}.NumberOfTrips ) AS SumNumberOfTrips,
               ArcID
        FROM routes_{0}
        LEFT JOIN trips_{0} ON routes_{0}.TripID = trips_{0}.ID
        WHERE ArcID IN ({1})
        GROUP BY DATE(trips_{0}.DateTime), ARCID
        """.format(self.scenarioID, ArcIDsStr)
        df = pd.read_sql(sql, self.connection)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')

        gp = df.groupby('ArcID')
        ndf = pd.DataFrame()
        for name, group in gp:
            ndf[name] = group['SumNumberOfTrips']

        return ndf

    def sqlAdvancedRoutes(self, group_by=['Vorm', 'NSTR']):
        """
        Advanced query for requesting all results in combinations of groupable parameters. The following groupings are possible:
        
        - TripsID: Generate statistics for all individual trips
        - Days: Generate output on daily frequency
        - NSTR: Classification of loads
        - Vorm: Classification of appearance type
        - Origin_Node: Group by node of origin port
        - Destination_Node: Group by node of destination port
        - Origin_NUTS3: Group by NUTS3 area of origins
        - Destination_NUTS3: Group by NUTS3 area of destinations
        """

        sql_select = ''
        sql_groupby = ''
        sql_leftjoin = ''
        sql_where = ''

        if not group_by:
            sql_groupby = 'Null'
        else:
            if 'TripsID' in group_by:
                sql_select += 'trips.ID AS "TripsID",'
                sql_groupby += 'trips.ID, '

            if 'Days' in group_by:
                sql_select += 'DATE(trips.DateTime) AS "Days",'
                sql_groupby += 'Days, '

            if 'NSTR' in group_by:
                sql_select += 'nstr_types.Code AS "NSTR",'
                sql_groupby += 'NstrTypeCode, '
                sql_leftjoin += 'LEFT JOIN nstr_types ON trips.NstrTypeCode = nstr_types.Code '

            if 'Vorm' in group_by:
                sql_select += 'appearance_types.Description AS "Vorm",'
                sql_groupby += 'trips.AppearanceTypeID, '
                sql_leftjoin += 'LEFT JOIN appearance_types ON trips.AppearanceTypeID = appearance_types.ID '

            if 'Origin_Node' in group_by:
                sql_select += 'trips.OriginTripEndPointNodeID AS "Origin_Node",'
                sql_select += 'nodes_origin.XCoordinate AS "Origin_X",'
                sql_select += 'nodes_origin.YCoordinate AS "Origin_Y",'
                sql_groupby += 'trips.OriginTripEndPointNodeID, '
                sql_leftjoin += 'LEFT JOIN nodes AS nodes_origin ON trips.OriginTripEndPointNodeID = nodes_origin.ID '

            if 'Destination_Node' in group_by:
                sql_select += 'trips.DestinationTripEndPointNodeID AS "Destination_Node",'
                sql_select += 'nodes_destination.XCoordinate AS "Destination_X",'
                sql_select += 'nodes_destination.YCoordinate AS "Destination_Y",'
                sql_groupby += 'trips.DestinationTripEndPointNodeID, '
                sql_leftjoin += 'LEFT JOIN nodes AS nodes_destination ON trips.DestinationTripEndPointNodeID = nodes_destination.ID '

            if 'Origin_NUTS3' in group_by:
                sql_leftjoin += 'LEFT JOIN zone_node_mapping ON trips.OriginTripEndPointNodeID = zone_node_mapping.NodeID '
                sql_leftjoin += 'LEFT JOIN zones ON zone_node_mapping.ZoneID = zones.ID '
                sql_groupby += 'zones.ID, '
                sql_select += 'zones.Name AS Origin_NUTS3, '
                sql_where += ' zones.ZoneDefinitionID = 7 AND zone_node_mapping.ZoneDefinitionID = 7 AND '

            if 'Destination_NUTS3' in group_by:
                sql_leftjoin += 'LEFT JOIN zone_node_mapping ON trips.DestinationTripEndPointNodeID = zone_node_mapping.NodeID '
                sql_leftjoin += 'LEFT JOIN zones ON zone_node_mapping.ZoneID = zones.ID '
                sql_groupby += 'zones.ID, '
                sql_select += 'zones.Name AS Destination_NUTS3, '
                sql_where += ' zones.ZoneDefinitionID = 7 AND zone_node_mapping.ZoneDefinitionID = 7 AND '

            sql_groupby = sql_groupby[:-2]
            sql_where = sql_where[:-5]

        if not sql_where:
            sql_where = '1'

        sql = """
        SELECT {sql_select}
               SUM(trips.NumberOfTrips) AS "Aantal Vaarbewegingen (-)",
               SUM(trips.TotalWeight__t * trips.NumberOfTrips) AS "Totale Vracht (ton)",
               SUM(trips.TwentyFeetEquivalentUnits * trips.NumberOfTrips) AS "Totale TEU (-)",
               SUM(route.TravelTime__min  * trips.NumberOfTrips) AS "Totale Reistijd (min)",
               SUM(route.VariableCosts__Eur  * trips.NumberOfTrips) + SUM(route.FixedCosts__Eur  * trips.NumberOfTrips) AS "Totale Vaarkosten (EUR)",
               SUM(route.VariableCosts__Eur * trips.NumberOfTrips) AS "Totale Variabele Vaarkosten (EUR)",
               SUM(route.FixedCosts__Eur * trips.NumberOfTrips) AS "Totale Vaste Vaarkosten (EUR)",
               SUM(route.Distance__km * trips.NumberOfTrips) AS "Totale Afstand (km)",
               SUM((trips.TotalWeight__t * route.Distance__km) * trips.NumberOfTrips) AS "Totale TonKM (TONKM)"
        FROM route_statistics_{id} AS route
        LEFT JOIN trips_{id} AS trips ON route.TripID = trips.ID
        {sql_leftjoin}
        WHERE {sql_where}
        GROUP BY {sql_groupby}
        """.format(id=self.scenarioID, sql_select=sql_select, sql_leftjoin=sql_leftjoin, sql_where=sql_where,
                   sql_groupby=sql_groupby)

        df = pd.read_sql(sql, self.connection)

        # Use short strings for NSTR classes
        df = df.replace({'NSTR': self.NSTR_shortnames})

        if group_by and 'Origin_NUTS3' in group_by:
            df['Afkorting'] = df['Origin_NUTS3'].str.split(pat=' - ', expand=True)[0]

        if group_by and 'Destination_NUTS3' in group_by:
            df['Afkorting'] = df['Destination_NUTS3'].str.split(pat=' - ', expand=True)[0]

        # Format dates
        if group_by and 'Days' in group_by:
            df['Days'] = pd.to_datetime(df['Days'])

        # TODO: Nog goede indexering (en volgorde) instellen
        if group_by:
            df = df.set_index(group_by).sort_index()
        return df

    def sqlArcDetails(self, arcID):
        """
        This function requests all vessel passing a specified arc with 
        various information about those vessels
        """
        sql = """
        SELECT trips.*,
               routes.OriginalArcDirection,
               ship_types.Label,
               ship_types.Description,
               nstr_types.Description AS nstr_description,
               appearance_types.Description AS appear_description,
               dangerous_goods_levels.Description AS dangerous_description
        FROM routes_{0} AS routes
        LEFT JOIN trips_{0} AS trips ON routes.TripID = trips.ID
        LEFT JOIN ship_types ON trips.ShipTypeID = ship_types.ID
        LEFT JOIN nstr_types ON trips.NstrTypeCode = nstr_types.Code
        LEFT JOIN appearance_types ON trips.AppearanceTypeID = appearance_types.ID
        LEFT JOIN dangerous_goods_levels ON trips.DangerousGoodsLevelID = dangerous_goods_levels.ID
        WHERE ArcID = {1}
        """.format(self.scenarioID, arcID)

        df = pd.read_sql(sql, self.connection)
        df = df.set_index('ID')
        df['DateTime'] = pd.to_datetime(df['DateTime'])
        df = df.drop(['SeasonID', 'ShipTypeID', 'DangerousGoodsLevelID', 'LoadTypeID'], axis=1)
        return df

    def sqlArcRouteStatistics(self, arcID):
        """
        Compute route statistics for a specific ArcID
        """
        sql = """
        SELECT trips.ID,
               (trips.NumberOfTrips) AS "Aantal Vaarbewegingen (-)",
               (trips.TotalWeight__t * trips.NumberOfTrips) AS "Totale Vracht (ton)",
               (trips.TwentyFeetEquivalentUnits * trips.NumberOfTrips) AS "Totale TEU (-)",
               (routeStats.Distance__km * trips.NumberOfTrips) AS "Totale Afstand (km)",
               (routeStats.TravelTime__min  * trips.NumberOfTrips) AS "Totale Reistijd (min)",
               (routeStats.VariableCosts__Eur  * trips.NumberOfTrips) + (routeStats.FixedCosts__Eur  * trips.NumberOfTrips) AS "Totale Vaarkosten (EUR)",
               (routeStats.VariableCosts__Eur * trips.NumberOfTrips) AS "Totale Variabele Vaarkosten (EUR)",
               (routeStats.FixedCosts__Eur * trips.NumberOfTrips) AS "Totale Vaste Vaarkosten (EUR)",
               ((trips.TotalWeight__t * routeStats.Distance__km) * trips.NumberOfTrips) AS "Totale TonKM (TONKM)"
        FROM routes_{0} AS routes
        LEFT JOIN trips_{0} AS trips ON routes.TripID = trips.ID
        LEFT JOIN route_statistics_{0} AS routeStats ON routeStats.TripID = routes.TripID
        WHERE ArcID = {1}
        """.format(self.scenarioID, arcID)

        df = self.sql(sql)
        df = df.set_index('ID')
        return df

    def sqlTripDetailsExpanded(self):
        """Get all trip properties"""
        sql = """
        SELECT trips.*,
               ship_types.Label,
               ship_types.Description,
               nstr_types.Description AS nstr_description,
               appearance_types.Description AS appear_description,
               dangerous_goods_levels.Description AS dangerous_description
        FROM trips_{0} AS trips
        LEFT JOIN ship_types ON trips.ShipTypeID = ship_types.ID
        LEFT JOIN nstr_types ON trips.NstrTypeCode = nstr_types.Code
        LEFT JOIN appearance_types ON trips.AppearanceTypeID = appearance_types.ID
        LEFT JOIN dangerous_goods_levels ON trips.DangerousGoodsLevelID = dangerous_goods_levels.ID
        """.format(self.scenarioID)

        df = pd.read_sql(sql, self.connection)
        df = df.set_index('ID')
        df['DateTime'] = pd.to_datetime(df['DateTime'])
        df = df.drop(['SeasonID', 'ShipTypeID', 'DangerousGoodsLevelID', 'LoadTypeID'], axis=1)

        return df

    def sqlRouteStatisticsForListTrips(self, tripsArray):
        """
        Get route statistics for an array of given trips
        """

        listOfTrips = ",".join(tripsArray.astype(str))

        sql = """
        SELECT trips.ID,
               (trips.NumberOfTrips) AS "Aantal Vaarbewegingen (-)",
               (trips.TotalWeight__t * trips.NumberOfTrips) AS "Totale Vracht (ton)",
               (trips.TwentyFeetEquivalentUnits * trips.NumberOfTrips) AS "Totale TEU (-)",
               (routeStats.Distance__km * trips.NumberOfTrips) AS "Totale Afstand (km)",
               (routeStats.TravelTime__min  * trips.NumberOfTrips) AS "Totale Reistijd (min)",
               (routeStats.VariableCosts__Eur  * trips.NumberOfTrips) + (routeStats.FixedCosts__Eur  * trips.NumberOfTrips) AS "Totale Vaarkosten (EUR)",
               (routeStats.VariableCosts__Eur * trips.NumberOfTrips) AS "Totale Variabele Vaarkosten (EUR)",
               (routeStats.FixedCosts__Eur * trips.NumberOfTrips) AS "Totale Vaste Vaarkosten (EUR)",
               ((trips.TotalWeight__t * routeStats.Distance__km) * trips.NumberOfTrips) AS "Totale TonKM (TONKM)"
            FROM trips_{0} AS trips
            LEFT JOIN route_statistics_{0} AS routeStats ON routeStats.TripID = trips.ID
            WHERE trips.ID IN ({1})
        """.format(self.scenarioID, listOfTrips)
        df2 = pd.read_sql(sql, self.connection)
        df2 = df2.set_index('ID')
        return df2

    def arcUsage(self):
        sql = """
        SELECT ArcID, 
        SUM(arcStats.NumberOfTrips) AS "Aantal Vaarbewegingen (-)",
        SUM(arcStats.NumberOfTrips * arcStats.AverageLoadWeight__t) AS "Totale Vracht (ton)",
        SUM(arcStats.AverageCosts__Eur / arcStats.AverageDistance__km) AS "Gemiddelde kosten/km"
        FROM arc_usage_statistics_details_{0} AS arcStats
        GROUP BY ArcID
        """.format(self.scenarioID)
        df = self.sql(sql)
        df = df.set_index('ArcID')
        return df

    """
    Network function
    """

    def sqlNetworkToNetworkx(self):
        """Create Networkx from arcs and nodes"""

        sql = """
        SELECT arcs.ID,
               arcs.Name,
               arcs.Length__m,
               arcs.FromNodeID,
               arcs.ToNodeID
        FROM arcs
        ORDER BY arcs.ID
        """
        arcs = pd.read_sql(sql, self.connection)

        sql = """
        SELECT *
        FROM nodes
        """
        nodes = pd.read_sql(sql, self.connection)
        nodes = nodes.set_index('ID')

        G = nx.from_pandas_edgelist(
            arcs, 'FromNodeID', 'ToNodeID', edge_attr=True)
        for n in nodes.iterrows():
            if n[0] in G.node:
                G.node[n[0]]['X'] = n[1]['XCoordinate']
                G.node[n[0]]['Y'] = n[1]['YCoordinate']
            else:
                pass
                print('Node {} is not connected to any edge'.format(n[0]))
        self.NetworkX = G
        return self.NetworkX

    def findPathInNetworkx(self, nodeidstart, nodeidend):
        """Find the path between two nodes
        Returns list of nodes and edges
        """
        if not hasattr(self, 'NetworkX'):
            self.sqlNetworkToNetworkx()

        pathnodes = nx.dijkstra_path(
            self.NetworkX, nodeidstart, nodeidend, weight='Length__m')
        pathedges = []
        for i in range(len(pathnodes) - 1):
            pathedges.append(
                self.NetworkX[pathnodes[i]][pathnodes[i + 1]]['ID'])
        return pathnodes, pathedges

    def findEdgesForNodes(self, pathnodes):
        """
        for each set of nodes, find the path between the nodes

        pathnodes={
        'Waal_Upstream':(6855,6799),
        'Waal_Downstream':(6799,7073)}
        """

        if not hasattr(self, 'NetworkX'):
            self.sqlNetworkToNetworkx()

        pathedges = {}
        for name, nodes in pathnodes.items():
            _, pathedges[name] = self.findPathInNetworkx(nodes[0], nodes[1])
        return pathedges

    """
    Compare two scenarios
    """

    def sqlCompareScenariosRoutes(self, casescenario):
        """Compare traveltimes of scenarios"""

        sql = """
        SELECT (route_statistics_{0}.TravelTime__min - route_statistics_{1}.TravelTime__min) AS ChangeInTravelTime,
                trips_{0}.NstrTypeCode AS NstrTypeCode,
                trips_{0}.TotalWeight__t * trips_{0}.NumberOfTrips AS TotalWeight__t,
                trips_{0}.NumberOfTrips AS nTrips
        FROM route_statistics_{0}
        LEFT JOIN route_statistics_{1} ON route_statistics_{0}.TripID = route_statistics_{1}.TripID
        LEFT JOIN trips_{0} ON route_statistics_{0}.TripID = trips_{0}.ID
        """.format(casescenario, self.scenarioID)
        df = pd.read_sql(sql, self.connection)
        return df

    def sqlCompareScenariosTrips(self, casescenario):
        """Compare increase in trips of routes in casescenario"""

        sql = """
        SELECT trips_{0}.NumberOfTrips - trips_{1}.NumberOfTrips AS ExtraTrips
        FROM trips_{0}
        RIGHT JOIN route_statistics_{0} ON route_statistics_{0}.TripID = trips_{0}.ID
        LEFT JOIN trips_{1} ON trips_{0}.ID = trips_{1}.ID
        """.format(casescenario, self.scenarioID)
        df = pd.read_sql(sql, self.connection)
        return df

    """
    Export to file
    """

    def sqlArcs(self, outputfileshape=None, outputfilecsv=None):
        """Export all Arcs in BIVAS to shapefile"""

        sql = """
        SELECT arcs.*,
               arc_types.Label,
               arc_types.Description,
               cemt_class.Description,
               cemt_class.MinimumAbsoluteUkc__m,
               cemt_class.MinimumRelativeUkc__m,
               N1.XCoordinate AS X1,
               N1.YCoordinate AS Y1,
               N2.XCoordinate AS X2,
               N2.YCoordinate AS Y2
        FROM arcs
        LEFT JOIN nodes AS N1 ON FromNodeID = N1.ID
        LEFT JOIN nodes AS N2 ON ToNodeID = N2.ID
        LEFT JOIN `branching$branch_sets` AS BS ON arcs.BranchSetID = BS.Id
        LEFT JOIN arc_types ON arcs.ArcTypeID = arc_types.ID
        LEFT JOIN cemt_class ON arcs.CemtClassId = cemt_class.ID
        WHERE BS.BranchID = {0}
        ORDER BY arcs.ID
        """.format(self.scenarioID)
        arcs = pd.read_sql(sql, self.connection).set_index('ID')

        arcs['XM'] = (arcs['X1'] + arcs['X2']) / 2
        arcs['YM'] = (arcs['Y1'] + arcs['Y2']) / 2

        if outputfilecsv:
            arcs.to_csv(outputfilecsv)

        arcs['geometry'] = arcs.apply(lambda z: LineString(
            [(z.X1, z.Y1), (z.X2, z.Y2)]), axis=1)
        arcsgpd = geopandas.GeoDataFrame(arcs)

        if outputfileshape:
            arcsgpd.to_file(outputfileshape)

        self.arcs = arcsgpd
        return self.arcs

    def sqlNodes(self, outputfile=None):
        """Export all Nodes in BIVAS to shapefile"""

        sql = """
        SELECT *
        FROM nodes
        """
        nodes = pd.read_sql(sql, self.connection).set_index('ID')
        # nodes = nodes.set_index('ID')
        nodes['geometry'] = nodes.apply(
            lambda z: Point(z.XCoordinate, z.YCoordinate), axis=1)

        nodes = geopandas.GeoDataFrame(nodes)
        if outputfile:
            nodes.to_file(outputfile)

        self.nodes = nodes
        return self.nodes

    """
    Single Route functions
    """

    def sqlRoute(self, routeID):
        """
        Load route on arcs for a specified RouteID

        requires the run of sqlArcs()
        """
        sql = """
        SELECT ArcID, OriginalArcDirection
        FROM routes_{0}
        WHERE TripID = {1}
        ORDER BY RouteIndex
        """.format(self.scenarioID, routeID)
        route = pd.read_sql(sql, self.connection)
        route = route.join(self.arcs, on='ArcID')
        route = geopandas.GeoDataFrame(route)
        return route

    def sqlRouteStats(self, routeID):
        """
        Load advanced route and shipstats for specified RouteID
        """
        sql = """
        SELECT  trips.*,
                route.*,
                nstr_types.Description AS nstr_description,
                appearance_types.Description AS appear_description,
                ship_types.Label AS ship_label,
                ship_types.Description as ship_description,
                dangerous_goods_levels.Description AS dangerous_description
        FROM route_statistics_{0} AS route
        LEFT JOIN trips_{0} AS trips ON route.TripID = trips.ID
        LEFT JOIN nstr_types ON trips.NstrTypeCode = nstr_types.Code
        LEFT JOIN appearance_types ON trips.AppearanceTypeID = appearance_types.ID
        LEFT JOIN ship_types ON trips.ShipTypeID = ship_types.ID
        LEFT JOIN dangerous_goods_levels ON trips.DangerousGoodsLevelID = dangerous_goods_levels.ID
        WHERE TripID = {1}
        """.format(self.scenarioID, routeID)
        routestats = pd.read_sql(sql, self.connection)
        return routestats

    # Get registered route of reference trips
    def sqlReferenceRoute(self, routeID, route, ReferenceSetID=3):
        """
        Validate the route of a routeID versus the reference tripset

        routeID = int
        route = output of sqlRoute
        ReferenceSetID = int (3 = IVS90_2014)

        requires the run of sqlArcs()
        """

        sql = """
        SELECT DateTime, Name, ArcID
        FROM reference_trip_set
        LEFT JOIN counting_points ON reference_trip_set.CountingPointID = counting_points.ID
        LEFT JOIN counting_point_arcs ON reference_trip_set.CountingPointID = counting_point_arcs.CountingPointID
        WHERE ReferenceSetID = {0}
        AND TripID = {1}
        ORDER BY DateTime
        """.format(ReferenceSetID, routeID)
        referencestrips = pd.read_sql(sql, self.connection)
        referencestrips = referencestrips.join(
            self.arcs, on='ArcID', rsuffix='_r')
        referencestrips = geopandas.GeoDataFrame(referencestrips)

        # Validate points passed
        referencestrips['PointPassed'] = np.in1d(
            referencestrips['ArcID'], route['ArcID'])
        referencestrips['geometry'] = referencestrips['geometry'].representative_point(
        )
        return referencestrips

    def sql(self, sql):
        """ Execute sql on loaded database"""
        return pd.read_sql(sql, self.connection)