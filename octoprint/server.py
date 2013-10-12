# coding=utf-8
__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

from werkzeug.utils import secure_filename
import tornadio2
from flask import Flask, request, render_template, jsonify, send_from_directory, url_for, current_app, session, abort, make_response
from flask.ext.login import LoginManager, login_user, logout_user, login_required, current_user
from flask.ext.principal import Principal, Permission, RoleNeed, Identity, identity_changed, AnonymousIdentity, identity_loaded, UserNeed

import os
import threading
import logging, logging.config
import subprocess

from octoprint.printer import Printer, getConnectionOptions
from octoprint.settings import settings, valid_boolean_trues
import octoprint.timelapse
import octoprint.gcodefiles as gcodefiles
import octoprint.util as util
import octoprint.users as users

import octoprint.events as events

SUCCESS = {}
BASEURL = "/ajax/"
APIBASEURL = "/api/"

app = Flask("octoprint")
# Only instantiated by the Server().run() method
# In order that threads don't start too early when running as a Daemon
printer = None
timelapse = None

gcodeManager = None
userManager = None
eventManager = None

principals = Principal(app)
admin_permission = Permission(RoleNeed("admin"))
user_permission = Permission(RoleNeed("user"))

#~~ Printer state

class PrinterStateConnection(tornadio2.SocketConnection):
	def __init__(self, printer, gcodeManager, userManager, eventManager, session, endpoint=None):
		tornadio2.SocketConnection.__init__(self, session, endpoint)

		self._logger = logging.getLogger(__name__)

		self._temperatureBacklog = []
		self._temperatureBacklogMutex = threading.Lock()
		self._logBacklog = []
		self._logBacklogMutex = threading.Lock()
		self._messageBacklog = []
		self._messageBacklogMutex = threading.Lock()

		self._printer = printer
		self._gcodeManager = gcodeManager
		self._userManager = userManager
		self._eventManager = eventManager

	def on_open(self, info):
		self._logger.info("New connection from client")
		# Use of global here is smelly
		self._printer.registerCallback(self)
		self._gcodeManager.registerCallback(self)

		self._eventManager.fire("ClientOpened")
		self._eventManager.subscribe("MovieDone", self._onMovieDone)

	def on_close(self):
		self._logger.info("Closed client connection")
		# Use of global here is smelly
		self._printer.unregisterCallback(self)
		self._gcodeManager.unregisterCallback(self)

		self._eventManager.fire("ClientClosed")
		self._eventManager.unsubscribe("MovieDone", self._onMovieDone)

	def on_message(self, message):
		pass

	def sendCurrentData(self, data):
		# add current temperature, log and message backlogs to sent data
		with self._temperatureBacklogMutex:
			temperatures = self._temperatureBacklog
			self._temperatureBacklog = []

		with self._logBacklogMutex:
			logs = self._logBacklog
			self._logBacklog = []

		with self._messageBacklogMutex:
			messages = self._messageBacklog
			self._messageBacklog = []

		data.update({
			"temperatures": temperatures,
			"logs": logs,
			"messages": messages
		})
		self.emit("current", data)

	def sendHistoryData(self, data):
		self.emit("history", data)

	def sendUpdateTrigger(self, type):
		self.emit("updateTrigger", type)

	def sendFeedbackCommandOutput(self, name, output):
		self.emit("feedbackCommandOutput", {"name": name, "output": output})

	def addLog(self, data):
		with self._logBacklogMutex:
			self._logBacklog.append(data)

	def addMessage(self, data):
		with self._messageBacklogMutex:
			self._messageBacklog.append(data)

	def addTemperature(self, data):
		with self._temperatureBacklogMutex:
			self._temperatureBacklog.append(data)

	def _onMovieDone(self, event, payload):
		self.sendUpdateTrigger("timelapseFiles")

# Did attempt to make webserver an encapsulated class but ended up with __call__ failures

@app.route("/")
def index():
	branch = None
	commit = None
	try:
		branch, commit = util.getGitInfo()
	except:
		pass

	return render_template(
		"index.jinja2",
		ajaxBaseUrl=BASEURL,
		webcamStream=settings().get(["webcam", "stream"]),
		enableTimelapse=(settings().get(["webcam", "snapshot"]) is not None and settings().get(["webcam", "ffmpeg"]) is not None),
		enableGCodeVisualizer=settings().get(["feature", "gCodeVisualizer"]),
		enableSystemMenu=settings().get(["system"]) is not None and settings().get(["system", "actions"]) is not None and len(settings().get(["system", "actions"])) > 0,
		enableAccessControl=userManager is not None,
		enableSdSupport=settings().get(["feature", "sdSupport"]),
		gitBranch=branch,
		gitCommit=commit
	)

#~~ Printer control

@app.route(BASEURL + "control/connection/options", methods=["GET"])
def connectionOptions():
	return jsonify(getConnectionOptions())

@app.route(BASEURL + "control/connection", methods=["POST"])
@login_required
def connect():
	if "command" in request.values.keys() and request.values["command"] == "connect":
		port = None
		baudrate = None
		if "port" in request.values.keys():
			port = request.values["port"]
		if "baudrate" in request.values.keys():
			baudrate = request.values["baudrate"]
		if "save" in request.values.keys():
			settings().set(["serial", "port"], port)
			settings().setInt(["serial", "baudrate"], baudrate)
			settings().save()
		if "autoconnect" in request.values.keys():
			settings().setBoolean(["serial", "autoconnect"], True)
			settings().save()
		printer.connect(port=port, baudrate=baudrate)
	elif "command" in request.values.keys() and request.values["command"] == "disconnect":
		printer.disconnect()

	return jsonify(SUCCESS)

@app.route(BASEURL + "control/command", methods=["POST"])
@login_required
def printerCommand():
	if "application/json" in request.headers["Content-Type"]:
		data = request.json

		parameters = {}
		if "parameters" in data.keys(): parameters = data["parameters"]

		commands = []
		if "command" in data.keys(): commands = [data["command"]]
		elif "commands" in data.keys(): commands = data["commands"]

		commandsToSend = []
		for command in commands:
			commandToSend = command
			if len(parameters) > 0:
				commandToSend = command % parameters
			commandsToSend.append(commandToSend)

		printer.commands(commandsToSend)

	return jsonify(SUCCESS)
	
@app.route(BASEURL + "control/spray", methods=["POST"])
@login_required
def printerSpray():
	if not printer.isOperational() or printer.isPrinting():
		# do not jog when a print job is running or we don't have a connection
		return jsonify(SUCCESS)

	if "distance" in request.values.keys():
		spray_distance = request.values["distance"]
		printer.command(";Distance :" + spray_distance)
		
	if "hight" in request.values.keys():
		spray_hight = request.values["hight"]
		printer.command(";Hight: " + spray_hight)	

	if "speed" in request.values.keys():
		spray_speed = request.values["speed"]
		printer.command(";Speed: " + spray_speed)	

	if "flow" in request.values.keys():
		spray_flow = request.values["flow"]
		printer.command(";Flow: " + spray_flow)	

	if "cycles" in request.values.keys():
		spray_cycles = request.values["cycles"]
		printer.command(";Cycles: " + spray_cycles)	

	if "delay" in request.values.keys():
		spray_delay = request.values["delay"]
		printer.command(";Delay: " + spray_delay)
		
	if "delay" in request.values.keys():
		spray_solution = request.values["solution"]
		printer.command(";Solution: " + spray_solution)
		
	filename = gcodeManager.getAbsolutePath("immediate.gcode", mustExist=False)
	printer.command(";" + filename)
	
	file = open(filename, "w")
	file.write( ";Spray file generated on the fly\n")

	###################section start###################
	# position constants
	sp_home_x = 0
	sp_home_y = 0
	sp_home_z = 0
	sp_offset = 0
	sp_x1 = -60
	sp_x2 = 60
	sp_y1 = -80
	sp_y2 = 80
	sp_top = 100
	sp_wash_x = 0
	sp_wash_y = -110
	sp_wash_z = -50
	# wash position top, use to approach
	sp_wash_u = -30

	# commands
	sc_valve_wash = "G1 V1\nG4 S1\n"
	sc_valve_spray = "G1 V2\nG4 S1\n"
	sc_valve_waste = "G1 V0\nG4 S1\n"
	#go to valve position % nr
	sc_valve_pos = "G1 V%d\nG4 S1\n"
	sc_air_on = "M106\n"
	sc_air_off = "M106 S0\n"

	# go to wash position
	sc_go_to_wash = ";go to wash\nG1 X%f" % sp_wash_x + " Y%f"  % sp_wash_y + " Z%f" % sp_wash_u + " F200\nG1 Z%f" % sp_wash_z  + " F200\n"

	# aspirate % position
	sc_aspirate = "G1 P%f F200\n"

	# set syringe to absolute mode
	sc_syringe_absolute= "M82\n"

	# set syringe to realtive mode
	sc_syringe_relative = "M83\n"

	# empty syringe
	sc_empty = "G1 P0 F200\n"

	# wait % seconds
	sc_wait = "G4 S%f\n"

	# set speed % speed
	sc_speed = "G1 F%f\n"

	# go to syringe position % position
	sc_syringe_position = "G1 P%f\n"

	# move fast % x, y position
	sc_move_fast = "G1 X%f Y%f F200\n"

	# move fast % z position
	sc_move_fast_z = "G1 Z%f F200\n"

	# spray fast % x, y, p, f
	sc_spray = "G1 X%f Y%f P%f F%f\n"

	# washing tip
	# a go to wash position
	sc_wash = "; wash\n"
	sc_wash += sc_go_to_wash
	# spray rest to waste
	sc_wash += sc_air_on
	sc_wash += sc_valve_waste + sc_empty
	# clean syringe with wash solution
	sc_wash += sc_valve_wash + sc_aspirate % 10
	sc_wash += sc_valve_waste + sc_empty
	# clean spray with wash solution
	sc_wash += sc_valve_wash + sc_aspirate % 10
	sc_wash += sc_valve_spray + sc_speed % 10 + sc_syringe_position % 0
	# drip wash solution from spray
	sc_wash += sc_air_off
	sc_wash += sc_valve_wash + sc_aspirate % 10
	sc_wash += sc_valve_spray + sc_speed % 10 + sc_syringe_position % 0
	# dry spray
	sc_wash += sc_air_on + "G4 S2\nG4 S2\nG4 S2\nG4 S2\n" + sc_air_off



	#coating starts
	file.write(";start coating\n")

	#flow in mm/s instead of mm/min
	spray_flow = spray_flow/60.0

	#syringe parameter in ul/mm
	spray_syringe_volume_per_travel = 5

	spray_lines = int((sp_y2 - sp_y1)/spray_distance)
	spray_travel_distance =  spray_lines * (sp_x2 - sp_x1) + 2 * (sp_y2 - sp_y1)
	spray_time = spray_travel_distance / spray_speed
	spray_syringe_volume = spray_time * spray_flow
	spray_syringe_travel = spray_syringe_volume / spray_syringe_volume_per_travel
	spray_syringe_x = (sp_x2 - sp_x1) / spray_speed * spray_flow / spray_syringe_volume_per_travel * -1
	spray_syringe_y = spray_distance / spray_speed * spray_flow / spray_syringe_volume_per_travel * -1

	# this is an intrinsic factor, test
	spray_feed = spray_speed * 4


	#prime system
	file.write(sc_valve_pos % spray_solution)
	file.write(sc_air_on)
	# prime spray with spray solution
	file.write(sc_aspirate % 5)
	file.write(sc_valve_spray + sc_speed % 10 + sc_syringe_position % 0)

	#start loop
	for n in range(spray_cycles):
		#aspirate syringe
		file.write(sc_valve_pos % spray_solution)
		file.write(sc_syringe_absolute)
		file.write(sc_aspirate % spray_syringe_travel)
		#move to start
		y_offset = spray_distance / spray_lines * n + sp_y1
		file.write(sc_move_fast % (sp_x1, y_offset))
		file.write(sc_move_fast_z % (spray_hight - sp_top))
		file.write(sc_syringe_relative)
		#spray cycle
		for y in range(spray_lines):
			if y % 2 == 0:
				#even
				file.write(sc_spray % (sp_x2, y_offset, spray_syringe_y, spray_feed))
				file.write(sc_spray % (sp_x1, y_offset, spray_syringe_x, spray_feed))
			elif y == 0:
				#first line
				file.write(sc_spray % (sp_x2, y_offset, spray_syringe_x, spray_feed))
			else:
			   #odd line
				file.write(sc_spray % (sp_x1, y_offset, spray_syringe_y, spray_feed))
				file.write(sc_spray % (sp_x2, y_offset, spray_syringe_x, spray_feed))

			y_offset += spray_distance

		#move to wash
		y_offset -= spray_distance
		file.write(sc_move_fast % (sp_x1, y_offset))
		file.write(sc_go_to_wash)

		#empty syringe
		file.write(sc_syringe_absolute)
		file.write(sc_valve_waste + sc_empty)
		#back to start

		#clean syringe


	# now do the wash
	file.write(sc_wash)
	
	###################section stop###################
	file.close()
	printer.selectFile(filename, False, True)

	return jsonify(SUCCESS)

@app.route(BASEURL + "control/job", methods=["POST"])
@login_required
def printJobControl():
	if "command" in request.values.keys():
		if request.values["command"] == "start":
			printer.startPrint()
		elif request.values["command"] == "pause":
			printer.togglePausePrint()
		elif request.values["command"] == "cancel":
			printer.cancelPrint()
	return jsonify(SUCCESS)

@app.route(BASEURL + "control/temperature", methods=["POST"])
@login_required
def setTargetTemperature():
	if "temp" in request.values.keys():
		# set target temperature
		temp = request.values["temp"]
		printer.command("M104 S" + temp)

	if "bedTemp" in request.values.keys():
		# set target bed temperature
		bedTemp = request.values["bedTemp"]
		printer.command("M140 S" + bedTemp)

	return jsonify(SUCCESS)

@app.route(BASEURL + "control/jog", methods=["POST"])
@login_required
def jog():
	if not printer.isOperational() or printer.isPrinting():
		# do not jog when a print job is running or we don't have a connection
		return jsonify(SUCCESS)

	(movementSpeedX, movementSpeedY, movementSpeedZ, movementSpeedE) = settings().get(["printerParameters", "movementSpeed", ["x", "y", "z", "e"]])
	if "x" in request.values.keys():
		# jog x
		x = request.values["x"]
		printer.commands(["G91", "G1 X%s F%d" % (x, movementSpeedX), "G90"])
	if "y" in request.values.keys():
		# jog y
		y = request.values["y"]
		printer.commands(["G91", "G1 Y%s F%d" % (y, movementSpeedY), "G90"])
	if "z" in request.values.keys():
		# jog z
		z = request.values["z"]
		printer.commands(["G91", "G1 Z%s F%d" % (z, movementSpeedZ), "G90"])
	if "homeXY" in request.values.keys():
		# home x/y
		printer.command("G28 X0 Y0")
	if "homeZ" in request.values.keys():
		# home z
		printer.command("G28 Z0")
	if "extrude" in request.values.keys():
		# extrude/retract
		length = request.values["extrude"]
		printer.commands(["G91", "G1 E%s F%d" % (length, movementSpeedE), "G90"])

	return jsonify(SUCCESS)

@app.route(BASEURL + "control/custom", methods=["GET"])
def getCustomControls():
	customControls = settings().get(["controls"])
	return jsonify(controls=customControls)

@app.route(BASEURL + "control/sd", methods=["POST"])
@login_required
def sdCommand():
	if not settings().getBoolean(["feature", "sdSupport"]) or not printer.isOperational() or printer.isPrinting():
		return jsonify(SUCCESS)

	if "command" in request.values.keys():
		command = request.values["command"]
		if command == "init":
			printer.initSdCard()
		elif command == "refresh":
			printer.refreshSdFiles()
		elif command == "release":
			printer.releaseSdCard()

	return jsonify(SUCCESS)

#~~ GCODE file handling

@app.route(BASEURL + "gcodefiles", methods=["GET"])
def readGcodeFiles():
	files = gcodeManager.getAllFileData()

	sdFileList = printer.getSdFiles()
	if sdFileList is not None:
		for sdFile in sdFileList:
			files.append({
				"name": sdFile,
				"size": "n/a",
				"bytes": 0,
				"date": "n/a",
				"origin": "sd"
			})
	return jsonify(files=files, free=util.getFormattedSize(util.getFreeBytes(settings().getBaseFolder("uploads"))))

@app.route(BASEURL + "gcodefiles/<path:filename>", methods=["GET"])
def readGcodeFile(filename):
	return send_from_directory(settings().getBaseFolder("uploads"), filename, as_attachment=True)

@app.route(BASEURL + "gcodefiles/upload", methods=["POST"])
@login_required
def uploadGcodeFile():
	if "gcode_file" in request.files.keys():
		file = request.files["gcode_file"]
		sd = "target" in request.values.keys() and request.values["target"] == "sd";

		currentFilename = None
		currentSd = None
		currentJob = printer.getCurrentJob()
		if currentJob is not None and "filename" in currentJob.keys() and "sd" in currentJob.keys():
			currentFilename = currentJob["filename"]
			currentSd = currentJob["sd"]

		futureFilename = gcodeManager.getFutureFilename(file)
		if futureFilename is None:
			return make_response("Can not upload file %s, wrong format?" % file.filename, 400)

		if futureFilename == currentFilename and sd == currentSd and printer.isPrinting() or printer.isPaused():
			# trying to overwrite currently selected file, but it is being printed
			return make_response("Trying to overwrite file that is currently being printed: %s" % currentFilename, 403)

		filename = gcodeManager.addFile(file)
		if filename is None:
			return make_response("Could not upload the file %s" % file.filename, 500)

		absFilename = gcodeManager.getAbsolutePath(filename)
		if sd:
			printer.addSdFile(filename, absFilename)

		if currentFilename == filename and currentSd == sd:
			# reload file as it was updated
			if sd:
				printer.selectFile(filename, sd, False)
			else:
				printer.selectFile(absFilename, sd, False)

		global eventManager
		eventManager.fire("Upload", filename)
	return jsonify(files=gcodeManager.getAllFileData(), filename=filename)


@app.route(BASEURL + "gcodefiles/load", methods=["POST"])
@login_required
def loadGcodeFile():
	if "filename" in request.values.keys():
		printAfterLoading = False
		if "print" in request.values.keys() and request.values["print"] in valid_boolean_trues:
			printAfterLoading = True

		sd = False
		if "target" in request.values.keys() and request.values["target"] == "sd":
			filename = request.values["filename"]
			sd = True
		else:
			filename = gcodeManager.getAbsolutePath(request.values["filename"])
		printer.selectFile(filename, sd, printAfterLoading)
	return jsonify(SUCCESS)

@app.route(BASEURL + "gcodefiles/delete", methods=["POST"])
@login_required
def deleteGcodeFile():
	if "filename" in request.values.keys():
		filename = request.values["filename"]
		sd = "target" in request.values.keys() and request.values["target"] == "sd"

		currentJob = printer.getCurrentJob()
		currentFilename = None
		currentSd = None
		if currentJob is not None and "filename" in currentJob.keys() and "sd" in currentJob.keys():
			currentFilename = currentJob["filename"]
			currentSd = currentJob["sd"]

		if currentFilename is not None and filename == currentFilename and not (printer.isPrinting() or printer.isPaused()):
			printer.unselectFile()

		if not (currentFilename == filename and currentSd == sd and (printer.isPrinting() or printer.isPaused())):
			if currentSd:
				printer.deleteSdFile(filename)
			else:
				gcodeManager.removeFile(filename)
	return readGcodeFiles()

@app.route(BASEURL + "gcodefiles/refresh", methods=["POST"])
@login_required
def refreshFiles():
	printer.updateSdFiles()
	return jsonify(SUCCESS)

#-- very simple api routines
@app.route(APIBASEURL + "load", methods=["POST"])
def apiLoad():
	logger = logging.getLogger(__name__)

	if not settings().get(["api", "enabled"]):
		abort(401)

	if not "apikey" in request.values.keys():
		abort(401)

	if request.values["apikey"] != settings().get(["api", "key"]):
		abort(403)

	if not "file" in request.files.keys():
		abort(400)

	# Perform an upload
	file = request.files["file"]
	filename = gcodeManager.addFile(file)
	if filename is None:
		logger.warn("Upload via API failed")
		abort(500)

	# Immediately perform a file select and possibly print too
	printAfterSelect = False
	if "print" in request.values.keys() and request.values["print"] in valid_boolean_trues:
		printAfterSelect = True
	filepath = gcodeManager.getAbsolutePath(filename)
	if filepath is not None:
		printer.selectFile(filepath, False, printAfterSelect)
	return jsonify(SUCCESS)

@app.route(APIBASEURL + "state", methods=["GET"])
def apiPrinterState():
	if not settings().get(["api", "enabled"]):
		abort(401)

	if not "apikey" in request.values.keys():
		abort(401)

	if request.values["apikey"] != settings().get(["api", "key"]):
		abort(403)

	currentData = printer.getCurrentData()
	currentData.update({
		"temperatures": printer.getCurrentTemperatures()
	})
	return jsonify(currentData)

#~~ timelapse handling

@app.route(BASEURL + "timelapse", methods=["GET"])
def getTimelapseData():
	global timelapse

	type = "off"
	additionalConfig = {}
	if timelapse is not None and isinstance(timelapse, octoprint.timelapse.ZTimelapse):
		type = "zchange"
	elif timelapse is not None and isinstance(timelapse, octoprint.timelapse.TimedTimelapse):
		type = "timed"
		additionalConfig = {
			"interval": timelapse.interval()
		}

	files = octoprint.timelapse.getFinishedTimelapses()
	for file in files:
		file["url"] = url_for("downloadTimelapse", filename=file["name"])

	return jsonify({
		"type": type,
		"config": additionalConfig,
		"files": files
	})

@app.route(BASEURL + "timelapse/<filename>", methods=["GET"])
def downloadTimelapse(filename):
	if util.isAllowedFile(filename, set(["mpg"])):
		return send_from_directory(settings().getBaseFolder("timelapse"), filename, as_attachment=True)

@app.route(BASEURL + "timelapse/<filename>", methods=["DELETE"])
@login_required
def deleteTimelapse(filename):
	if util.isAllowedFile(filename, set(["mpg"])):
		secure = os.path.join(settings().getBaseFolder("timelapse"), secure_filename(filename))
		if os.path.exists(secure):
			os.remove(secure)
	return getTimelapseData()

@app.route(BASEURL + "timelapse", methods=["POST"])
@login_required
def setTimelapseConfig():
	global timelapse

	if request.values.has_key("type"):
		type = request.values["type"]
		if type in ["zchange", "timed"]:
			# valid timelapse type, check if there is an old one we need to stop first
			if timelapse is not None:
				timelapse.unload()
			timelapse = None
		if "zchange" == type:
			timelapse = octoprint.timelapse.ZTimelapse()
		elif "timed" == type:
			interval = 10
			if request.values.has_key("interval"):
				try:
					interval = int(request.values["interval"])
				except ValueError:
					pass
			timelapse = octoprint.timelapse.TimedTimelapse(interval)

	return getTimelapseData()

#~~ settings

@app.route(BASEURL + "settings", methods=["GET"])
def getSettings():
	s = settings()

	[movementSpeedX, movementSpeedY, movementSpeedZ, movementSpeedE] = s.get(["printerParameters", "movementSpeed", ["x", "y", "z", "e"]])

	connectionOptions = getConnectionOptions()

	return jsonify({
		"api": {
			"enabled": s.getBoolean(["api", "enabled"]),
			"key": s.get(["api", "key"])
		},
		"appearance": {
			"name": s.get(["appearance", "name"]),
			"color": s.get(["appearance", "color"])
		},
		"printer": {
			"movementSpeedX": movementSpeedX,
			"movementSpeedY": movementSpeedY,
			"movementSpeedZ": movementSpeedZ,
			"movementSpeedE": movementSpeedE,
		},
		"webcam": {
			"streamUrl": s.get(["webcam", "stream"]),
			"snapshotUrl": s.get(["webcam", "snapshot"]),
			"ffmpegPath": s.get(["webcam", "ffmpeg"]),
			"bitrate": s.get(["webcam", "bitrate"]),
			"watermark": s.getBoolean(["webcam", "watermark"]),
			"flipH": s.getBoolean(["webcam", "flipH"]),
			"flipV": s.getBoolean(["webcam", "flipV"])
		},
		"feature": {
			"gcodeViewer": s.getBoolean(["feature", "gCodeVisualizer"]),
			"waitForStart": s.getBoolean(["feature", "waitForStartOnConnect"]),
			"alwaysSendChecksum": s.getBoolean(["feature", "alwaysSendChecksum"]),
			"sdSupport": s.getBoolean(["feature", "sdSupport"])
		},
		"serial": {
			"port": connectionOptions["portPreference"],
			"baudrate": connectionOptions["baudratePreference"],
			"portOptions": connectionOptions["ports"],
			"baudrateOptions": connectionOptions["baudrates"],
			"autoconnect": s.getBoolean(["serial", "autoconnect"]),
			"timeoutConnection": s.getFloat(["serial", "timeout", "connection"]),
			"timeoutDetection": s.getFloat(["serial", "timeout", "detection"]),
			"timeoutCommunication": s.getFloat(["serial", "timeout", "communication"]),
			"log": s.getBoolean(["serial", "log"])
		},
		"folder": {
			"uploads": s.getBaseFolder("uploads"),
			"timelapse": s.getBaseFolder("timelapse"),
			"timelapseTmp": s.getBaseFolder("timelapse_tmp"),
			"logs": s.getBaseFolder("logs")
		},
		"temperature": {
			"profiles": s.get(["temperature", "profiles"])
		},
		"system": {
			"actions": s.get(["system", "actions"]),
			"events": s.get(["system", "events"])
		} 
	})

@app.route(BASEURL + "settings", methods=["POST"])
@login_required
@admin_permission.require(403)
def setSettings():
	if "application/json" in request.headers["Content-Type"]:
		data = request.json
		s = settings()

		if "api" in data.keys():
			if "enabled" in data["api"].keys(): s.set(["api", "enabled"], data["api"]["enabled"])
			if "key" in data["api"].keys(): s.set(["api", "key"], data["api"]["key"], True)

		if "appearance" in data.keys():
			if "name" in data["appearance"].keys(): s.set(["appearance", "name"], data["appearance"]["name"])
			if "color" in data["appearance"].keys(): s.set(["appearance", "color"], data["appearance"]["color"])

		if "printer" in data.keys():
			if "movementSpeedX" in data["printer"].keys(): s.setInt(["printerParameters", "movementSpeed", "x"], data["printer"]["movementSpeedX"])
			if "movementSpeedY" in data["printer"].keys(): s.setInt(["printerParameters", "movementSpeed", "y"], data["printer"]["movementSpeedY"])
			if "movementSpeedZ" in data["printer"].keys(): s.setInt(["printerParameters", "movementSpeed", "z"], data["printer"]["movementSpeedZ"])
			if "movementSpeedE" in data["printer"].keys(): s.setInt(["printerParameters", "movementSpeed", "e"], data["printer"]["movementSpeedE"])

		if "webcam" in data.keys():
			if "streamUrl" in data["webcam"].keys(): s.set(["webcam", "stream"], data["webcam"]["streamUrl"])
			if "snapshotUrl" in data["webcam"].keys(): s.set(["webcam", "snapshot"], data["webcam"]["snapshotUrl"])
			if "ffmpegPath" in data["webcam"].keys(): s.set(["webcam", "ffmpeg"], data["webcam"]["ffmpegPath"])
			if "bitrate" in data["webcam"].keys(): s.set(["webcam", "bitrate"], data["webcam"]["bitrate"])
			if "watermark" in data["webcam"].keys(): s.setBoolean(["webcam", "watermark"], data["webcam"]["watermark"])
			if "flipH" in data["webcam"].keys(): s.setBoolean(["webcam", "flipH"], data["webcam"]["flipH"])
			if "flipV" in data["webcam"].keys(): s.setBoolean(["webcam", "flipV"], data["webcam"]["flipV"])

		if "feature" in data.keys():
			if "gcodeViewer" in data["feature"].keys(): s.setBoolean(["feature", "gCodeVisualizer"], data["feature"]["gcodeViewer"])
			if "waitForStart" in data["feature"].keys(): s.setBoolean(["feature", "waitForStartOnConnect"], data["feature"]["waitForStart"])
			if "alwaysSendChecksum" in data["feature"].keys(): s.setBoolean(["feature", "alwaysSendChecksum"], data["feature"]["alwaysSendChecksum"])
			if "sdSupport" in data["feature"].keys(): s.setBoolean(["feature", "sdSupport"], data["feature"]["sdSupport"])

		if "serial" in data.keys():
			if "autoconnect" in data["serial"].keys(): s.setBoolean(["serial", "autoconnect"], data["serial"]["autoconnect"])
			if "port" in data["serial"].keys(): s.set(["serial", "port"], data["serial"]["port"])
			if "baudrate" in data["serial"].keys(): s.setInt(["serial", "baudrate"], data["serial"]["baudrate"])
			if "timeoutConnection" in data["serial"].keys(): s.setFloat(["serial", "timeout", "connection"], data["serial"]["timeoutConnection"])
			if "timeoutDetection" in data["serial"].keys(): s.setFloat(["serial", "timeout", "detection"], data["serial"]["timeoutDetection"])
			if "timeoutCommunication" in data["serial"].keys(): s.setFloat(["serial", "timeout", "communication"], data["serial"]["timeoutCommunication"])

			oldLog = s.getBoolean(["serial", "log"])
			if "log" in data["serial"].keys(): s.setBoolean(["serial", "log"], data["serial"]["log"])
			if oldLog and not s.getBoolean(["serial", "log"]):
				# disable debug logging to serial.log
				logging.getLogger("SERIAL").debug("Disabling serial logging")
				logging.getLogger("SERIAL").setLevel(logging.CRITICAL)
			elif not oldLog and s.getBoolean(["serial", "log"]):
				# enable debug logging to serial.log
				logging.getLogger("SERIAL").setLevel(logging.DEBUG)
				logging.getLogger("SERIAL").debug("Enabling serial logging")

		if "folder" in data.keys():
			if "uploads" in data["folder"].keys(): s.setBaseFolder("uploads", data["folder"]["uploads"])
			if "timelapse" in data["folder"].keys(): s.setBaseFolder("timelapse", data["folder"]["timelapse"])
			if "timelapseTmp" in data["folder"].keys(): s.setBaseFolder("timelapse_tmp", data["folder"]["timelapseTmp"])
			if "logs" in data["folder"].keys(): s.setBaseFolder("logs", data["folder"]["logs"])

		if "temperature" in data.keys():
			if "profiles" in data["temperature"].keys(): s.set(["temperature", "profiles"], data["temperature"]["profiles"])

		if "system" in data.keys():
			if "actions" in data["system"].keys(): s.set(["system", "actions"], data["system"]["actions"])
			if "events" in data["system"].keys(): s.set(["system", "events"], data["system"]["events"])
		s.save()

	return getSettings()

#~~ user settings

@app.route(BASEURL + "users", methods=["GET"])
@login_required
@admin_permission.require(403)
def getUsers():
	if userManager is None:
		return jsonify(SUCCESS)

	return jsonify({"users": userManager.getAllUsers()})

@app.route(BASEURL + "users", methods=["POST"])
@login_required
@admin_permission.require(403)
def addUser():
	if userManager is None:
		return jsonify(SUCCESS)

	if "application/json" in request.headers["Content-Type"]:
		data = request.json

		name = data["name"]
		password = data["password"]
		active = data["active"]

		roles = ["user"]
		if "admin" in data.keys() and data["admin"]:
			roles.append("admin")

		try:
			userManager.addUser(name, password, active, roles)
		except users.UserAlreadyExists:
			abort(409)
	return getUsers()

@app.route(BASEURL + "users/<username>", methods=["GET"])
@login_required
def getUser(username):
	if userManager is None:
		return jsonify(SUCCESS)

	if current_user is not None and not current_user.is_anonymous() and (current_user.get_name() == username or current_user.is_admin()):
		user = userManager.findUser(username)
		if user is not None:
			return jsonify(user.asDict())
		else:
			abort(404)
	else:
		abort(403)

@app.route(BASEURL + "users/<username>", methods=["PUT"])
@login_required
@admin_permission.require(403)
def updateUser(username):
	if userManager is None:
		return jsonify(SUCCESS)

	user = userManager.findUser(username)
	if user is not None:
		if "application/json" in request.headers["Content-Type"]:
			data = request.json

			# change roles
			roles = ["user"]
			if "admin" in data.keys() and data["admin"]:
				roles.append("admin")
			userManager.changeUserRoles(username, roles)

			# change activation
			if "active" in data.keys():
				userManager.changeUserActivation(username, data["active"])
		return getUsers()
	else:
		abort(404)

@app.route(BASEURL + "users/<username>", methods=["DELETE"])
@login_required
@admin_permission.require(http_exception=403)
def removeUser(username):
	if userManager is None:
		return jsonify(SUCCESS)

	try:
		userManager.removeUser(username)
		return getUsers()
	except users.UnknownUser:
		abort(404)

@app.route(BASEURL + "users/<username>/password", methods=["PUT"])
@login_required
def changePasswordForUser(username):
	if userManager is None:
		return jsonify(SUCCESS)

	if current_user is not None and not current_user.is_anonymous() and (current_user.get_name() == username or current_user.is_admin()):
		if "application/json" in request.headers["Content-Type"]:
			data = request.json
			if "password" in data.keys() and data["password"]:
				try:
					userManager.changeUserPassword(username, data["password"])
				except users.UnknownUser:
					return app.make_response(("Unknown user: %s" % username, 404, []))
		return jsonify(SUCCESS)
	else:
		return app.make_response(("Forbidden", 403, []))

#~~ system control

@app.route(BASEURL + "system", methods=["POST"])
@login_required
@admin_permission.require(403)
def performSystemAction():
	logger = logging.getLogger(__name__)
	if request.values.has_key("action"):
		action = request.values["action"]
		availableActions = settings().get(["system", "actions"])
		for availableAction in availableActions:
			if availableAction["action"] == action:
				logger.info("Performing command: %s" % availableAction["command"])
				try:
					subprocess.check_output(availableAction["command"], shell=True)
				except subprocess.CalledProcessError, e:
					logger.warn("Command failed with return code %i: %s" % (e.returncode, e.message))
					return app.make_response(("Command failed with return code %i: %s" % (e.returncode, e.message), 500, []))
				except Exception, ex:
					logger.exception("Command failed")
					return app.make_response(("Command failed: %r" % ex, 500, []))
	return jsonify(SUCCESS)

#~~ Login/user handling

@app.route(BASEURL + "login", methods=["POST"])
def login():
	if userManager is not None and "user" in request.values.keys() and "pass" in request.values.keys():
		username = request.values["user"]
		password = request.values["pass"]

		if "remember" in request.values.keys() and request.values["remember"] == "true":
			remember = True
		else:
			remember = False

		user = userManager.findUser(username)
		if user is not None:
			if user.check_password(users.UserManager.createPasswordHash(password)):
				login_user(user, remember=remember)
				identity_changed.send(current_app._get_current_object(), identity=Identity(user.get_id()))
				return jsonify(user.asDict())
		return app.make_response(("User unknown or password incorrect", 401, []))
	elif "passive" in request.values.keys():
		user = current_user
		if user is not None and not user.is_anonymous():
			identity_changed.send(current_app._get_current_object(), identity=Identity(user.get_id()))
			return jsonify(user.asDict())
	return jsonify(SUCCESS)

@app.route(BASEURL + "logout", methods=["POST"])
@login_required
def logout():
	# Remove session keys set by Flask-Principal
	for key in ('identity.id', 'identity.auth_type'):
		del session[key]
	identity_changed.send(current_app._get_current_object(), identity=AnonymousIdentity())

	logout_user()

	return jsonify(SUCCESS)

@identity_loaded.connect_via(app)
def on_identity_loaded(sender, identity):
	user = load_user(identity.id)
	if user is None:
		return

	identity.provides.add(UserNeed(user.get_name()))
	if user.is_user():
		identity.provides.add(RoleNeed("user"))
	if user.is_admin():
		identity.provides.add(RoleNeed("admin"))

def load_user(id):
	if userManager is not None:
		return userManager.findUser(id)
	return users.DummyUser()

#~~ startup code
class Server():
	def __init__(self, configfile=None, basedir=None, host="0.0.0.0", port=5000, debug=False):
		self._configfile = configfile
		self._basedir = basedir
		self._host = host
		self._port = port
		self._debug = debug

		  
	def run(self):
		# Global as I can't work out a way to get it into PrinterStateConnection
		global printer
		global gcodeManager
		global userManager
		global eventManager
		
		from tornado.wsgi import WSGIContainer
		from tornado.httpserver import HTTPServer
		from tornado.ioloop import IOLoop
		from tornado.web import Application, FallbackHandler

		# first initialize the settings singleton and make sure it uses given configfile and basedir if available
		self._initSettings(self._configfile, self._basedir)

		# then initialize logging
		self._initLogging(self._debug)
		logger = logging.getLogger(__name__)

		eventManager = events.eventManager()
		gcodeManager = gcodefiles.GcodeManager()
		printer = Printer(gcodeManager)

		# setup system and gcode command triggers
		events.SystemCommandTrigger(printer)
		events.GcodeCommandTrigger(printer)
		if self._debug:
			events.DebugEventListener()

		if settings().getBoolean(["accessControl", "enabled"]):
			userManagerName = settings().get(["accessControl", "userManager"])
			try:
				clazz = util.getClass(userManagerName)
				userManager = clazz()
			except AttributeError, e:
				logger.exception("Could not instantiate user manager %s, will run with accessControl disabled!" % userManagerName)

		app.secret_key = "k3PuVYgtxNm8DXKKTw2nWmFQQun9qceV"
		login_manager = LoginManager()
		login_manager.session_protection = "strong"
		login_manager.user_callback = load_user
		if userManager is None:
			login_manager.anonymous_user = users.DummyUser
			principals.identity_loaders.appendleft(users.dummy_identity_loader)
		login_manager.init_app(app)

		if self._host is None:
			self._host = settings().get(["server", "host"])
		if self._port is None:
			self._port = settings().getInt(["server", "port"])

		logger.info("Listening on http://%s:%d" % (self._host, self._port))
		app.debug = self._debug

		self._router = tornadio2.TornadioRouter(self._createSocketConnection)

		self._tornado_app = Application(self._router.urls + [
			(".*", FallbackHandler, {"fallback": WSGIContainer(app)})
		])
		self._server = HTTPServer(self._tornado_app)
		self._server.listen(self._port, address=self._host)

		eventManager.fire("Startup")
		if settings().getBoolean(["serial", "autoconnect"]):
			(port, baudrate) = settings().get(["serial", "port"]), settings().getInt(["serial", "baudrate"])
			connectionOptions = getConnectionOptions()
			if port in connectionOptions["ports"]:
				printer.connect(port, baudrate)
		IOLoop.instance().start()

	def _createSocketConnection(self, session, endpoint=None):
		global printer, gcodeManager, userManager, eventManager
		return PrinterStateConnection(printer, gcodeManager, userManager, eventManager, session, endpoint)

	def _initSettings(self, configfile, basedir):
		s = settings(init=True, basedir=basedir, configfile=configfile)

	def _initLogging(self, debug):
		config = {
			"version": 1,
			"formatters": {
				"simple": {
					"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
				}
			},
			"handlers": {
				"console": {
					"class": "logging.StreamHandler",
					"level": "DEBUG",
					"formatter": "simple",
					"stream": "ext://sys.stdout"
				},
				"file": {
					"class": "logging.handlers.TimedRotatingFileHandler",
					"level": "DEBUG",
					"formatter": "simple",
					"when": "D",
					"backupCount": "1",
					"filename": os.path.join(settings().getBaseFolder("logs"), "octoprint.log")
				},
				"serialFile": {
					"class": "logging.handlers.RotatingFileHandler",
					"level": "DEBUG",
					"formatter": "simple",
					"maxBytes": 2 * 1024 * 1024, # let's limit the serial log to 2MB in size
					"filename": os.path.join(settings().getBaseFolder("logs"), "serial.log")
				}
			},
			"loggers": {
				#"octoprint.timelapse": {
				#	"level": "DEBUG"
				#},
				#"octoprint.events": {
				#	"level": "DEBUG"
				#},
				"SERIAL": {
					"level": "CRITICAL",
					"handlers": ["serialFile"],
					"propagate": False
				}
			},
			"root": {
				"level": "INFO",
				"handlers": ["console", "file"]
			}
		}

		if debug:
			config["root"]["level"] = "DEBUG"

		logging.config.dictConfig(config)

if __name__ == "__main__":
	octoprint = Server()
	octoprint.run()
