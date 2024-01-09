import pandas as pd
import numpy as np
import scipy as sp
import math 
import collections
import openpyxl
import matplotlib.pyplot as plt
import io
import plotly.express as px
from sklearn.preprocessing import StandardScaler
import pypsa


network = pypsa.Network()
hours_in_2015 = pd.date_range('2015-01-01T00:00Z','2015-12-31T23:00Z', freq='H')
network.set_snapshots(hours_in_2015)
network.add("Bus","electricity bus")
#print(network.snapshots) 


# load electricity demand data
df_elec = pd.read_csv('time_series_60min_singleindex.csv', sep=',', index_col=0) # in MWh
df_elec.index = pd.to_datetime(df_elec.index) #change index to datatime
#print(df_elec['GB_GBN_wind_generation_actual'].head())

# add load to the bus
network.add("Load",
            "load", 
            bus="electricity bus", 
            p_set=df_elec['GB_GBN_load_actual_entsoe_transparency'])


print(network.loads_t.p_set)
print(len(network.loads_t.p_set))

def annuity(n,r):
    """Calculate the annuity factor for an asset with lifetime n years and
    discount rate of r, e.g. annuity(20,0.05)*20 = 1.6"""

    if r > 0:
        return r/(1. - 1./(1.+r)**n)
    else:
        return 1/n

# add the different carriers, only gas emits CO2
network.add("Carrier", "onshorewind") # in t_CO2/MWh_th
network.add("Carrier", "offshorewind")
network.add("Carrier", "solar")
network.add("Carrier", "gas", co2_emissions=0.185)

# add onshore wind generator
df_onshorewind = pd.read_csv('onshore_wind_1979-2017.csv', sep=';', index_col=0)
df_onshorewind.index = pd.to_datetime(df_onshorewind.index)


CF_wind = df_onshorewind['GBR'][[hour.strftime("%Y-%m-%dT%H:%M:%SZ") for hour in network.snapshots]] #https://www.grantthornton.co.uk/globalassets/1.-member-firms/united-kingdom/pdf/documents/renewable-energy-discount-rate-survey-results-2018.pdf
#CF_wind = np.load("CF_wind_2011.npy")
#np.save("CF_wind_2011.npy",CF_wind)

capital_cost_onshorewind = annuity(25,0.08)*52910*(1) # in €/MW  https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/911817/electricity-generation-cost-report-2020.pdf
network.add("Generator",
            "onshorewind",
            bus="electricity bus",
            p_nom_extendable=True,
            carrier="onshorewind",
            #p_nom_max=1000, # maximum capacity can be limited due to environmental constraints
            capital_cost = capital_cost_onshorewind,
            marginal_cost = 0,
            p_max_pu = CF_wind)

# add offshore wind generator
df_offshorewind = pd.read_csv('offshore_wind_1979-2017.csv', sep=';', index_col=0)
df_offshorewind.index = pd.to_datetime(df_offshorewind.index)
CF_wind_offshore = df_offshorewind['GBR'][[hour.strftime("%Y-%m-%dT%H:%M:%SZ") for hour in network.snapshots]]
#CF_wind_offshore = np.load("CF_wind_offshore_2011.npy")
#np.save("CF_wind_offshore_2011.npy",CF_wind_offshore)

capital_cost_offshorewind = annuity(25,0.0875)*65560*(1) # in €/MW 910000
network.add("Generator",
            "offshorewind",
            bus="electricity bus",
            p_nom_extendable=True,
            carrier="offshorewind",
            #p_nom_max=1000, # maximum capacity can be limited due to environmental constraints
            capital_cost = capital_cost_offshorewind,
            marginal_cost = 0,
            p_max_pu = CF_wind_offshore)

# add solar PV generator
df_solar = pd.read_csv('pv_optimal.csv', sep=';', index_col=0)
df_solar.index = pd.to_datetime(df_solar.index)
CF_solar = df_solar['GBR'][[hour.strftime("%Y-%m-%dT%H:%M:%SZ") for hour in network.snapshots]]
#CF_solar = np.load("CF_solar_2011.npy")
#np.save("CF_solar_2011.npy",CF_solar)

capital_cost_solar = annuity(25,0.07)*50610*(1) # in €/MW 
network.add("Generator",
            "solar",
            bus="electricity bus",
            p_nom_extendable=True,
            carrier="solar",
            #p_nom_max=1000, # maximum capacity can be limited due to environmental constraints
            capital_cost = capital_cost_solar,
            marginal_cost = 0,
            p_max_pu = CF_solar)



# add OCGT (Open Cycle Gas Turbine) generator
capital_cost_OCGT = annuity(25,0.07)*930700*(1) # in €/MW #https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/315717/coal_and_gas_assumptions.PDF
fuel_cost = 14.71 # in €/MWh_th #https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/1107499/quarterly_energy_prices_uk_september_2022.pdf
efficiency = 0.38 #https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/387566/Technical_Assessment_of_the_Operation_of_Coal_and_Gas_Plant_PB_Power_FIN....pdf
marginal_cost_OCGT = fuel_cost/efficiency # in €/MWh_el
network.add("Generator", 
            "OCGT",
            bus="electricity bus",
            p_nom_extendable=True,
            carrier="gas",
            #p_nom_max=1000,
            capital_cost = capital_cost_OCGT,
            marginal_cost = marginal_cost_OCGT)

network.lopf(network.snapshots, 
             pyomo=False,
             solver_name='gurobi')


print (network.generators_t.p_max_pu) # in MW
print ((network.generators.p_nom_opt/1000)) # /in GW
print(network.objective/network.loads_t.p.sum()) # €/MWh

efficiency_bat = 0.85 #https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/910261/storage-costs-technical-assumptions-2018.pdf
Store_cap_bat = 4000
network.add("StorageUnit",
            "Battery",
            bus="electricity bus",
            p_nom = Store_cap_bat * efficiency_bat,
            max_hours=1, #energy storage in terms of hours at full power
            capital_cost_Bat = annuity(15,0.07)*674210*(1) # in €/MW #https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/910261/storage-costs-technical-assumptions-2018.pdf
           )

efficiency_hydrogen = 0.75
Store_cap_hydrogen = 123000  #https://www.british-hydro.org/wp-content/uploads/2018/03/Pumped-Storage-report.pdf
network.add("StorageUnit",
            "Hydrogen",
            bus="electricity bus",
            p_nom = Store_cap_hydrogen * efficiency_hydrogen,
            max_hours=1, #energy storage in terms of hours at full power
            capital_cost_hydrogen = annuity(30,0.07)*1558110*(1+0.033) # in €/MW
           )

network.lopf(network.snapshots, 
             pyomo=False,
             solver_name='gurobi')
print ((network.generators.p_nom_opt/1000)) # /in GW

print(network.objective/network.loads_t.p.sum()) # €/MWh

# Plot figure regarding 7th of August
plt.plot(network.loads_t.p['load'][5232:5256], color='black', label='demand') #5040:5136 504:648
plt.plot(network.generators_t.p['onshorewind'][5232:5256], color='blue', label='onshore wind')
plt.plot(network.generators_t.p['offshorewind'][5232:5256], color='green', label='offshore wind')
plt.plot(network.generators_t.p['solar'][5232:5256], color='orange', label='solar')
plt.plot(network.generators_t.p['OCGT'][5232:5256], color='brown', label='gas (OCGT)')
plt.plot(network.storage_units_t.p['Battery'][5232:5256], color='lightgreen', label='Battery')
plt.plot(network.storage_units_t.p['Hydrogen'][5232:5256], color='purple', label='Hydrogen')
###plt.plot(network.generators_t.p['coal'][5376:5544], color='Navy', label='Coal')
plt.legend(fancybox=True, shadow=True, loc='best')
plt.xlabel('Month-Date Hour') 
plt.ylabel('Power (MW)') 
plt.show()

#Plot figure regarding 22nd of January
plt.plot(network.loads_t.p['load'][504:528], color='black', label='demand') #5040:5136 504:648
plt.plot(network.generators_t.p['onshorewind'][504:528], color='blue', label='onshore wind')
plt.plot(network.generators_t.p['offshorewind'][504:528], color='green', label='offshore wind')
plt.plot(network.generators_t.p['solar'][504:528], color='orange', label='solar')
plt.plot(network.generators_t.p['OCGT'][504:528], color='brown', label='gas (OCGT)')
plt.plot(network.storage_units_t.p['Battery'][504:528], color='lightgreen', label='Battery')
plt.plot(network.storage_units_t.p['Hydrogen'][504:528], color='purple', label='Hydrogen')
###plt.plot(network.generators_t.p['coal'][5376:5544], color='Navy', label='Coal')
plt.legend(fancybox=True, shadow=True, loc='best')
plt.xlabel('Month-Date Hour') 
plt.ylabel('Power (MW)') 
plt.show()


# Plot figure regarding summer
plt.plot(network.loads_t.p['load'][4104:6336], color='black', label='demand') #5040:5136 504:648
plt.plot(network.generators_t.p['onshorewind'][4104:6480], color='blue', label='onshore wind')
plt.plot(network.generators_t.p['offshorewind'][4104:6480], color='green', label='offshore wind')
plt.plot(network.generators_t.p['solar'][4104:6480], color='orange', label='solar')
plt.plot(network.generators_t.p['OCGT'][34104:6480], color='brown', label='gas (OCGT)')
plt.plot(network.storage_units_t.p['Battery'][4104:6480], color='lightgreen', label='Battery')
plt.plot(network.storage_units_t.p['Hydrogen'][4104:6480], color='purple', label='Hydrogen')
###plt.plot(network.generators_t.p['coal'][5376:5544], color='Navy', label='Coal')
plt.legend(fancybox=True, shadow=True, loc='best')
plt.xlabel('Month-Date Hour') 
plt.ylabel('Power (MW)') 
plt.show()


# Plot figure regarding winter
plt.plot(network.loads_t.p['load'][1:1920], color='black', label='demand') #5040:5136 504:648
plt.plot(network.generators_t.p['onshorewind'][1:1920], color='blue', label='onshore wind')
plt.plot(network.generators_t.p['offshorewind'][1:1920], color='green', label='offshore wind')
plt.plot(network.generators_t.p['solar'][1:1920], color='orange', label='solar')
plt.plot(network.generators_t.p['OCGT'][1:1920], color='brown', label='gas (OCGT)')
plt.plot(network.storage_units_t.p['Battery'][1:1920], color='lightgreen', label='Battery')
plt.plot(network.storage_units_t.p['Hydrogen'][1:1920], color='purple', label='Hydrogen')
###plt.plot(network.generators_t.p['coal'][5376:5544], color='Navy', label='Coal')
plt.legend(fancybox=True, shadow=True, loc='best')
plt.xlabel('Month-Date Hour') 
plt.ylabel('Power (MW)') 
plt.show()