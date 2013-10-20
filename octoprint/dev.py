spray_distance = float("5")
spray_hight = 60
spray_speed = 180
spray_flow = 0.2
spray_cycles = 2
spray_delay = 1
spray_solution = 4


filename = "C:/Users/stoecma2/Desktop/test.gcode"
	
file = open(filename, "w")
file.write( ";Spray file generated on the fly\n")

if 1:
	###################section start###################
	# position constants
	sp_home_x = 0.0
	sp_home_y = 0.0
	sp_home_z = 0.0
	sp_offset = 0.0
	sp_x1 = -60.0
	sp_x2 = 60.0
	sp_y1 = -80.0
	sp_y2 = 80.0
	sp_top = 100.0
	sp_wash_x = 0.0
	sp_wash_y = -110.0
	sp_wash_z = -50.0
	# wash position top, use to approach
	sp_wash_u = -30.0

	# commands
	sc_valve_wash = "G1 V2 F200\nG4 S1\n"
	sc_valve_spray = "G1 V1 F200\nG4 S1\n"
	sc_valve_waste = "G1 V0 F200\nG4 S1\n"
	#go to valve position % nr
	sc_valve_pos = "G1 V{} F200\nG4 S1\n"
	sc_air_on = "M106\n"
	sc_air_off = "M106 S0\n"
	sc_init = "G28XYZ\nG28P\n"
	sc_motor_off = "M18\n"

	# go to wash position
	sc_go_to_wash = ";go to wash\nG1 X{} Y{} Z{} F200\nG1 Z{}\n".format (sp_wash_x, sp_wash_y, sp_wash_u, sp_wash_z)

	# aspirate % position
	sc_aspirate = "G1 P{} F200\n"

	# set syringe to absolute mode
	sc_syringe_absolute= "M82\n"

	# set syringe to realtive mode
	sc_syringe_relative = "M83\n"

	# empty syringe
	sc_empty = "G1 P0 F200\n"

	# wait % seconds
	sc_wait = "G4 S{}\n"

	# set speed % speed
	sc_speed = "G1 F{}\n"

	# go to syringe position % position
	sc_syringe_position = "G1 P{}\n"

	# move fast % x, y position
	sc_move_fast = "G1 X{} Y{} F200\n"

	# move fast % z position
	sc_move_fast_z = "G1 Z{} F200\n"

	# spray fast % x, y, p, f
	sc_spray = "G1 X{} Y{} P{} F{}\n"

	sc_go_home = "G1 X0 Y0 Z0 F200\n"

	# washing tip
	# a go to wash position
	sc_wash = "; wash\n"
	sc_wash += sc_syringe_absolute
	sc_wash += sc_go_to_wash
	# spray rest to waste
	sc_wash += sc_air_on
	sc_wash += sc_valve_waste + sc_empty
	# clean syringe with wash solution
	sc_wash += sc_valve_wash + sc_aspirate.format(10)
	sc_wash += sc_valve_waste + sc_empty
	# clean spray with wash solution
	sc_wash += sc_valve_wash + sc_aspirate.format(4)
	sc_wash += sc_valve_spray + sc_speed.format(0.5) + sc_syringe_position.format(0)
	# drip wash solution from spray
	sc_wash += sc_air_off
	sc_wash += sc_valve_wash + sc_aspirate.format(3)
	sc_wash += sc_valve_spray + sc_speed.format(0.2) + sc_syringe_position.format(0)
	sc_wash += sc_syringe_position.format(1)
	sc_wash += sc_air_on
	sc_wash += sc_syringe_position.format(0)

	# priming system
	sc_prime ="; prime\n" + sc_init
	sc_prime += sc_syringe_absolute
	sc_prime += sc_valve_wash + sc_aspirate.format(10) + sc_valve_waste + sc_empty
	sc_prime += sc_valve_pos.format(3) + sc_aspirate.format(10) + sc_valve_waste + sc_empty
	sc_prime += sc_valve_pos.format(4) + sc_aspirate.format(10) + sc_valve_waste + sc_empty
	sc_prime += sc_valve_pos.format(5) + sc_aspirate.format(10) + sc_valve_waste + sc_empty
	sc_prime += sc_valve_wash + sc_aspirate.format(10) + sc_valve_waste + sc_empty

	# purge system
	sc_purge ="; purge\n" + sc_init
	sc_purge += sc_syringe_absolute
	sc_purge += sc_valve_wash + sc_aspirate.format(10) + sc_valve_waste + sc_empty
	sc_purge += sc_valve_wash + sc_aspirate.format(10) + sc_valve_waste + sc_empty
	sc_purge += sc_valve_wash + sc_aspirate.format(10) + sc_valve_waste + sc_empty


	# dry spray
	sc_wash += sc_air_on + "G4 S2\nG4 S2\nG4 S2\nG4 S2\n" + sc_air_off

	#coating starts
	file.write(";start coating\n")
	file.write(sc_init)

	#syringe parameter in ul/mm
	spray_syringe_volume_per_travel = 29
	
	#flow contains ul/cm^2
	#densitity in ul/mm
	spray_density = float(spray_flow)/100 * spray_distance

	spray_lines = int((sp_y2 - sp_y1)/spray_distance)
	spray_travel_distance =  spray_lines * (sp_x2 - sp_x1) + (sp_y2 - sp_y1)
	spray_time = spray_travel_distance / spray_speed

	spray_syringe_volume = spray_travel_distance * spray_density
	spray_syringe_travel = spray_syringe_volume / spray_syringe_volume_per_travel

	spray_syringe_x = (sp_x2 - sp_x1) * spray_density / spray_syringe_volume_per_travel * -1
	spray_syringe_y = spray_distance * spray_density / spray_syringe_volume_per_travel * -1
	
	# this is an intrinsic factor, test
	spray_feed = spray_speed * 1.0
	
	#prime system
	file.write(sc_go_to_wash)
	file.write(sc_valve_pos.format(spray_solution))
	file.write(sc_air_on)
	# prime spray with spray solution
	file.write(sc_aspirate.format(2))
	file.write(sc_valve_spray + sc_speed.format(0.5) + sc_syringe_position.format(0))

	#start loop
	for n in range(spray_cycles):
		#aspirate syringe
		file.write(sc_air_on)
		file.write(sc_syringe_absolute)
		file.write(sc_valve_pos.format(spray_solution))
		file.write(sc_aspirate.format(spray_syringe_travel + 2))
		file.write(sc_valve_spray)		
		file.write(sc_speed.format(0.5) + sc_syringe_position.format(spray_syringe_travel))
		file.write(sc_move_fast_z.format(sp_wash_u))

		#move to start
		y_offset = spray_distance / spray_lines * n + sp_y1
		file.write(sc_move_fast.format(sp_x1, y_offset))
		file.write(sc_move_fast_z.format((spray_hight - sp_top)))
		file.write(sc_syringe_relative)
		#spray cycle
		for y in range(spray_lines):
			if y % 2 == 0:
				#even
				file.write(sc_spray.format(sp_x2, y_offset, spray_syringe_y, spray_feed))
				file.write(sc_spray.format(sp_x1, y_offset, spray_syringe_x, spray_feed))
			elif y == 0:
				#first line
				file.write(sc_spray.format(sp_x2, y_offset, spray_syringe_x, spray_feed))
			else:
			   #odd line
				file.write(sc_spray.format(sp_x1, y_offset, spray_syringe_y, spray_feed))
				file.write(sc_spray.format(sp_x2, y_offset, spray_syringe_x, spray_feed))

			y_offset += spray_distance

		#move to wash
		file.write("G1 Y{} Z{} F200".format(sp_y1, sp_wash_u))
		file.write(sc_go_to_wash)

		#empty syringe
		file.write(sc_syringe_absolute)
		file.write(sc_valve_waste + sc_empty)
		#back to start

		#clean syringe

		if n != int(spray_cycles):
			file.write(sc_air_off)
			file.write(sc_wait.format(spray_delay))
	# now do the wash
	file.write(sc_air_off)
	file.write(sc_wash)
	file.write(sc_go_home)
	file.write(sc_motor_off)
	file.write(sc_prime)
	file.write(sc_purge)

	###################section stop###################

file.close()