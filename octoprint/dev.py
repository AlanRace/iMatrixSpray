spray_distance = 10.0
spray_hight = 50
spray_speed = 10
spray_flow = 10
spray_cycles = 1
spray_delay = 0
spray_solution = 1


filename = 'C:\Users\stoecma2\Desktop\test.gcode'
	
file = open(filename, "w")
file.write( ";Spray file generated on the fly\n")

if 1:
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