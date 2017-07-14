#!/usr/bin/env python3
#


# import modules used here -- sys is a very standard one
import sys,argparse,logging,os,json,subprocess
from string import Template
from libraries import utility
from libraries.plugin_loader import run_plugin


#Getting path for config usage

current_dir = os.path.dirname(os.path.abspath(__file__))
configuration = None
config_path = current_dir+"/../config/tbng.json"
runtime= {}
runtime_path = current_dir+"/../config/runtime.json"


torrc="/etc/tor/torrc"
config_prefix='#TBNG_Autogenerated_-_do_not_edit_'

# Gather our code in a main() function
def main(args, loglevel):
  global configuration
  global runtime
  logging.basicConfig(format="%(levelname)s: %(message)s", level=loglevel)

  with open(config_path) as data_file:    
    configuration = json.load(data_file)
  logging.debug("Configuration loaded from file {0}".format(config_path))

    
  if os.path.isfile(runtime_path):
    with open(runtime_path) as data_file:    
      runtime = json.load(data_file)
    logging.debug("Runtime data loaded from file {0}".format(runtime_path))
  else:
    ### default runtime is here
    runtime['mode']="direct"
    runtime['tor_bridges']={}
    runtime['tor_bridges']['mode']="none"
    runtime['tor_bridges']['bridges']=[]
    runtime['tor_excluded_countries']=[]
    logging.debug("Runtime not found, creating default")
    update_runtime()
   
  logging.debug("Configuration dump: {0}".format(configuration))
  logging.debug("Runtime dump: {0}".format(runtime))
  # Actual code starts here
  logging.debug("We are running in {0}".format(current_dir))
  logging.debug("Your Command: {0}".format(args.command))
  logging.debug("Options are: {0}".format(args.options))
  
  choices = {   #do not use ()
   'chkconfig': chkconfig,   # checks config
   'masquerade': masquerade, # enables masquerading on all outbound interfaces
   'clean_firewall': clean_fw, # cleans firewall
   'mode': mode, # sets mode -direct,tor,privoxy, restore
   'reboot': reboot, #reboots
   'shutdown': shutdown, #shutdowns
   'tor_restart': tor_restart, #restarts tor
   'i2p_restart': i2p_restart, #(re)starts i2p
   'i2p_stop': i2p_stop, #stops i2p
   'get_default_interface': get_default_interface, #prints default interface or raises an exception in case iface not in list
   'set_default_interface': set_default_interface, #sets default interface, raises exception if interface not in wan list.
   'probe_obfs': probe_obfs, #returns possible obfsproxy options
   'tor_bridge': tor_bridge, #configures tor bridge
   'tor_reset': tor_reset, #removes tor settings for bridge and for countries
   'tor_exclude_exit': tor_exclude_exit, #exclude exit nodes by country
   'get_cpu_temp': get_cpu_temp, #get cpu temperature
   'unknown': unknown, # stub for unknown option
  }
  
  runfunc = choices[args.command] if choices.get(args.command) else unknown
  runfunc(args.options)  
  
#options checker

def check_options(options,num):
  if num!=len(options):
    raise Exception("Illegal number of options, required number is {0}".format(num))  

#function implementation goes here
def unknown(options):
 raise Exception("Unknown options passed")

def chkconfig(options):
  check_options(options,0)
  ##getting interface list
  iface_list = os.listdir("/sys/class/net")
  logging.debug("Interface list: {0}".format(iface_list))
  ##checking WAN interfaces
  wireless=0
  wired=0

  if ('wan_interface' not in configuration.keys()) or (not configuration['wan_interface']):
   raise Exception("No WAN interfaces configured")
     
  for interface in configuration['wan_interface']:
    if interface['name'] not in iface_list:
      raise Exception("WAN interface {0} is not defined or does not exist in /sys/class/net".format(interface['name']))
    else: 
      if is_wireless(configuration['wan_interface'],interface['name']):
        wireless +=1
      else:
        wired +=1

  if ( wireless > 1 ) or ( wired > 1 ):
    raise Exception("Only one interface of same type is allowed - wired or wireless")

  #checking LAN Interfaces
  if ('lan_interface' not in configuration.keys()) or (not configuration['lan_interface']):
   raise Exception("No LAN interface configured")

  for interface in configuration['lan_interface']:
    if interface['name'] not in iface_list:
      raise Exception("LAN interface {0} is not defined or does not exist in /sys/class/net".format(interface['name']))
  
  #Checking interface conflicts
  lans=[]
  for interface in configuration['lan_interface']:
    lans.append(interface['name'])
  wans=[]
  for interface in configuration['wan_interface']:
    wans.append(interface['name'])

  if len(set(lans).intersection(wans)) > 0:
   raise Exception("Conflicting interfaces in LAN and WAN are detected: {0}".format(set(lans).intersection(wans)))
 

  logging.info("Check config called")

def masquerade(options):
  check_options(options,0)
  # template
  tmplScript=""
  # Making list of wan interfaces

  for interface in configuration['wan_interface']:
    tmplScript = tmplScript + "$iptables --table nat --append POSTROUTING --out-interface {0} -j MASQUERADE\n".format(interface['name']) 
  
  for interface in configuration['lan_interface']:
    tmplScript = tmplScript + "$iptables --append FORWARD --in-interface {0} -j ACCEPT\n".format(interface['name']) 

  tmplScript = tmplScript + "$iptables -A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT\n" 
  tmplScript = tmplScript + "sysctl -w net.ipv4.ip_forward=1\n"

  logging.debug(utility.run_multi_shell_command(Template(tmplScript).substitute(iptables=configuration["iptables"])).decode("utf-8"))
  logging.info("Masquerading called")

def clean_fw(options):
  check_options(options,0)
  logging.debug(utility.run_multi_shell_command(Template("""$iptables -F
  $iptables -X
  $iptables -t nat -F
  $iptables -t nat -X
  $iptables -t mangle -F
  $iptables -t mangle -X
  $iptables -t raw -F
  $iptables -t raw -X
  $iptables -P INPUT ACCEPT
  $iptables -P FORWARD ACCEPT
  $iptables -P OUTPUT ACCEPT""").substitute(iptables=configuration["iptables"])).decode("utf-8"))
  logging.info("Clean firewall called")

def mode(options):
  check_options(options,1)
  
  if options[0] not in  ['direct','tor','privoxy','restore']:
    raise Exception("Illegal mode")
  

  commandModeTemplate=""
  for interface in configuration['lan_interface']:
    if options[0] == 'privoxy':
      commandModeTemplate  += "$iptables -t nat -A PREROUTING -i {0} -p tcp --dport 80 -j REDIRECT --to-port 8118\n".format(interface['name'])
    commandModeTemplate += "$iptables -t nat -A PREROUTING -i {0} -p udp --dport 53 -j REDIRECT --to-ports 9053\n".format(interface['name'])  
    commandModeTemplate += "$iptables -t nat -A PREROUTING -i {0} -p tcp --syn -j REDIRECT --to-ports 9040\n".format(interface['name'])

  if options[0] == 'restore':
    options[0] = runtime['mode']

  clean_fw([])

  #Allowing desired ports
  allowed_ports = [22,3000,7657,9050,8118] + configuration['allowed_ports']
  
  commandAllowTemplate="sysctl -w net.ipv4.ip_forward=1\n" #must run always
  for interface in configuration['lan_interface']:
    for port in allowed_ports:
      commandAllowTemplate = commandAllowTemplate + "$iptables -t nat -A PREROUTING -i {0} -p tcp --dport {1} -j REDIRECT --to-port {2}\n".format(interface['name'],port,port)  
  logging.debug(utility.run_multi_shell_command(Template(commandAllowTemplate).substitute(iptables=configuration["iptables"])).decode("utf-8"))

  if options[0] in ['tor','privoxy']:
    command = Template(commandModeTemplate).substitute(iptables=configuration["iptables"])
    logging.debug("Running command: \n{0}\n".format(command))
    logging.debug(utility.run_multi_shell_command(command).decode("utf-8"))
  else:
    masquerade([])

  #Locking firewall if needed
  commandLockTemplate = "$iptables  -A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT\n"
  for interface in configuration['wan_interface']:
   commandLockTemplate = commandLockTemplate + "$iptables -A INPUT -i {0} -j DROP\n".format(interface['name'])
  
  if configuration['lock_firewall']:
    logging.debug(utility.run_multi_shell_command(Template(commandLockTemplate).substitute(iptables=configuration["iptables"])).decode("utf-8"))
  
  runtime['mode']=options[0]
  update_runtime()

  #calling tor_bridges

  tor_bridge([json.dumps(runtime['tor_bridges'])])
  tor_exclude_exit([json.dumps(runtime['tor_excluded_countries'])])

  logging.info("Mode setting called - mode {0} selected".format(options[0]))  

def reboot(options):
  check_options(options,0)
  logging.info("Reboot called")
  logging.debug(utility.run_shell_command("reboot").decode("utf-8"))
  
def shutdown(options):
  check_options(options,0)
  logging.info("Shutdown called")
  logging.debug(utility.run_shell_command("shutdown -h now").decode("utf-8"))

def tor_restart(options):
  check_options(options,0)
  logging.debug(utility.run_shell_command("systemctl restart tor").decode("utf-8"))
  logging.info("TOR Restart called")

def i2p_restart(options):
  check_options(options,0)
  logging.debug(utility.run_shell_command("systemctl restart i2p-torbox").decode("utf-8"))
  logging.info("I2P Restart called")  

def i2p_stop(options):
  check_options(options,0)
  logging.debug(utility.run_shell_command("systemctl stop i2p-torbox").decode("utf-8"))
  logging.info("I2P Stop called")

def get_default_interface(options):
  check_options(options,0)
  interface_name=utility.run_piped(["ip","r","g","1.1.1.1"],["sed","-rn","s/^.*dev ([^ ]*).*$/\\1/p"])[0].decode("utf-8").strip()
  logging.debug("Return value: {0}".format(interface_name))
  interface_known=False
  for interface in configuration['wan_interface']:
    if interface['name'] == interface_name:
     interface_known=True
     break
  
  if interface_known:
    print(interface_name)
  else:
    raise Exception("Interface is unknown or not configured")


def set_default_interface(options):
  check_options(options,1)
  wan = []
  for i in configuration['wan_interface']:
     wan.append(i['name'])
  if options[0] not in wan:
    raise Exception("Interface not configured WAN interfaces list.")
  command=""  
  for i in wan:
    device_managed=is_managed(i)
    if device_managed:
      command += "nmcli dev {0} disconnect\n".format(i)
    else:
      command += "ifdown {0}\n".format(i)

  if is_managed(options[0]):
   command += "nmcli dev connect {0}\n".format(options[0])
  else:
   command += "ifup {0}\n".format(options[0]) 
 
  logging.debug(command)
  logging.debug(utility.run_shell_command(command).decode("utf-8"))
  logging.info("Set default interface {0} called".format(options[0]))

def probe_obfs(options):
  check_options(options,0)
  obfs_options = {}
  obfs_options['none']=""
  obfs3=probe_obfs_binary("obfs3")
  obfs4=probe_obfs_binary("obfs4")

  if obfs3:
    obfs_options['obfs3']=obfs3

  if obfs4:
    obfs_options['obfs4']=obfs4
  
  print(json.dumps(obfs_options))

def probe_obfs_binary(mode):
  retval=""
  if mode == "obfs3":
    try:
      retval = utility.run_shell_command("which obfsproxy").decode("utf-8").strip()
    except subprocess.CalledProcessError as e:
      logging.debug(e.output)
  elif mode == "obfs4":
     try:
       retval = utility.run_shell_command("which obfs4proxy").decode("utf-8").strip()
     except subprocess.CalledProcessError as e:
       logging.debug(e.output)
  else:
    raise Exception("Unsupported bridge mode")

  return retval


def tor_bridge(options):
  config_section="_tor_bridges_"
  check_options(options,1)
  obfs_setting = json.loads(options[0])

  config_update="""UseBridges 1
"""

  if obfs_setting['mode'] not in ['none','obfs3','obfs4']:
    raise Exception("Invalid bridge mode {0} specified".format(obfs_setting['mode']))

  runtime['tor_bridges']={}
  runtime['tor_bridges']['mode']=obfs_setting['mode']
  runtime['tor_bridges']['bridges']=obfs_setting['bridges']
  utility.removeFileData(torrc,config_prefix,config_section)
  
  if not obfs_setting['mode']=='none':
    for obfs_string in obfs_setting['bridges']:
      if not obfs_string.startswith( obfs_setting['mode']):
        raise Exception("Invalid bridge setting applied")
      else:
        config_update += "Bridge "+obfs_string + "\n"
    
    config_update += "ClientTransportPlugin " + obfs_setting['mode'] + " exec " + probe_obfs_binary(obfs_setting['mode'])

    if obfs_setting['mode']=='obfs3':
      config_update += " --managed"
    config_update +="\n"
    utility.appendFileData(torrc,config_prefix,config_section,config_update)
  
  try:  
    tor_restart([])
    update_runtime()
  except subprocess.CalledProcessError as e:
    utility.removeFileData(torrc,config_prefix,config_section)
    runtime['tor_bridges']={}
    runtime['tor_bridges']['mode']="none"
    runtime['tor_bridges']['bridges']=[]
    update_runtime()
    tor_restart([])
    raise Exception("There was an error restarting TOR after bridge update. Bridge disabled, TOR restarted.")
  logging.info("TOR Bridge called") 

def tor_reset(options):
  check_options(options,0)
  tor_bridge(['{"mode": "none", "bridges": []}'])
  tor_exclude_exit(['[]'])
  logging.info("TOR Reset called")


def tor_exclude_exit(options):
  check_options(options,1)
  config_section="_tor_countries_exclude_"  
  #load country codes from country file
  torcountry_path = current_dir+"/../config/torcountry.json"
  with open(torcountry_path) as data_file:
    torcountry = json.load(data_file)
  logging.debug("TOR country codes  loaded from file {0}".format(torcountry_path))  
  #parse json input for list
  provided_countries = json.loads(options[0])

  #check, that provided countries are in country list
  if provided_countries:
    Found=False
    for country in provided_countries:
      Found=False
      for listed_country in torcountry:
        Found = (listed_country['code'] == country)
        if Found:
          break

    if not Found:
      raise Exception("Country code provided is not valid - update countries list or correct the argument")
  
  utility.removeFileData(torrc,config_prefix,config_section)

  if provided_countries:
    runtime['tor_excluded_countries']=provided_countries
    config_update = "ExcludeExitNodes "
    for country in provided_countries:
      config_update += "{"+country +"},"
    utility.appendFileData(torrc,config_prefix,config_section,config_update)
  else:
    runtime['tor_excluded_countries']=[]

  try:
    tor_restart([])
    update_runtime()
  except subprocess.CalledProcessError as e:
    utility.removeFileData(torrc,config_prefix,config_section)
    runtime['tor_excluded_countries']=[]
    update_runtime()
    tor_restart([])
    raise Exception("There was an error restarting TOR after country list update. Exit nodes ban disabled, TOR restarted.")
  logging.info("TOR Exclude exit called")
  
def get_cpu_temp(options):
  check_options(options,0)
  retval="Temperature monitoring not supported"
  if configuration['cputemp']:
    retval=run_plugin("cputemp",configuration['cputemp'])
  print("{0}".format(retval))
  

def is_managed(interface):
  command="nmcli dev show {0}|grep unmanaged||true".format(interface)
  return "unmanaged" not in utility.run_shell_command(command).decode("utf-8") 
    
def is_wireless(section,name):
  interface_found=False
  logging.debug("is_wireless called with section: {0} and name: {1}".format(section,name)) 
  for interface in section:
    if interface['name']==name:
      interface_found=True                         
      if 'wireless' in interface and interface['wireless']:
        return True
  if not interface_found:
    raise Exception("Interface not found.")
  return False   

def update_runtime():
  with open(runtime_path, 'w') as outfile:
    json.dump(runtime, outfile)
  logging.debug("Runtime updated at {0}".format(runtime_path))
  logging.info("Runtime updated called")
 
# Standard boilerplate to call the main() function to begin
# the program.

if sys.version_info[0] < 3:
    raise Exception("Python 3.x is required.")

if not os.geteuid()==0:
 raise Exception("sudo or root is required.")

if __name__ == '__main__':
  parser = argparse.ArgumentParser( 
                                    description = "Commands executor for TBNG project.",
                                    epilog = "As an alternative to the commandline, params can be placed in a file, one per line, and specified on the commandline like '%(prog)s @params.conf'.",
                                    fromfile_prefix_chars = '@' )

  parser.add_argument(
                      "command",
                      help = "pass command to the program",
                      metavar = "command")

  parser.add_argument(
                      "options",
                      help = "pass command options to the program (optional)",
                      metavar = "options",
                      nargs = '*',
                      default = [])

 
  parser.add_argument(
                      "-v",
                      "--verbose",
                      help="increase output verbosity",
                      action="store_true")
  args = parser.parse_args()
  
  # Setup logging
  if args.verbose:
    loglevel = logging.DEBUG
  else:
    loglevel = logging.INFO

  
  main(args, loglevel)
