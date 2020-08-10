import csv
import os
import math


metadata = {
    'protocolName': 'Station C Thermo Taqpath Multiple Single-Plex',
    'author': 'Chaz <protocols@opentrons.com>',
    'source': 'Custom Protocol Request',
    'apiLevel': '2.4'
}


NUM_SAMPLES = 8  # start with 8 samples; max is 32
SAMPLE_VOL = 5
PREPARE_MASTERMIX = True
TIP_TRACK = False


def run(protocol):

    source_plate = protocol.load_labware(
        'opentrons_96_aluminumblock_nest_wellplate_100ul', '1',
        'chilled elution plate on block from Station B')
    tips20 = [
        protocol.load_labware('opentrons_96_filtertiprack_20ul', slot)
        for slot in ['3', '6', '8', '9', '10', '11']
    ]
    tips300 = [protocol.load_labware('opentrons_96_filtertiprack_200ul', '2')]
    tempdeck = protocol.load_module('Temperature Module Gen2', '4')
    pcr_plate = tempdeck.load_labware(
        'opentrons_96_aluminumblock_nest_wellplate_100ul', 'PCR plate')
    strip_labware = protocol.load_labware(
        'opentrons_96_aluminumblock_generic_pcr_strip_200ul', '7',
        'mastermix strips')
    tempdeck.set_temperature(4)
    tube_block = protocol.load_labware(
        'opentrons_24_aluminumblock_nest_2ml_screwcap', '5',
        '2ml screw tube aluminum block for mastermix + controls')

    num_cols = math.ceil(NUM_SAMPLES/8)
    mm_wells = tube_block.wells()[:3]
    mm_strip = strip_labware.rows()[0][:3]
    mm_strip_single = strip_labware.columns()[:3]

    mm_cols = [pcr_plate.rows()[0][i:i+num_cols] for i in [0, 4, 8]]

    samples = source_plate.rows()[0][:num_cols]

    # pipette
    m20 = protocol.load_instrument('p20_multi_gen2', 'right', tip_racks=tips20)
    p300 = protocol.load_instrument('p300_single_gen2', 'left', tip_racks=tips300)

    # Tip tracking between runs
    if not protocol.is_simulating():
        file_path = '/data/csv/tiptracking.csv'
        file_dir = os.path.dirname(file_path)
        # check for file directory
        if not os.path.exists(file_dir):
            os.makedirs(file_dir)
        # check for file; if not there, create initial tip count tracking
        if not os.path.isfile(file_path):
            with open(file_path, 'w') as outfile:
                outfile.write("0, 0\n")

    tip_count_list = []
    if protocol.is_simulating() or not TIP_TRACK:
        tip_count_list = [0, 0]
    else:
        with open(file_path) as csv_file:
            csv_reader = csv.reader(csv_file, delimiter=',')
            tip_count_list = next(csv_reader)

    t20count = int(tip_count_list[0])
    t20max = len(tips20)*12
    t300count = int(tip_count_list[1])
    t300max = len(tips300)*96

    tip_tracker = {m20: [t20count, t20max], p300: [t300count, t300max]}

    def pick_up(pip):
        nonlocal tip_tracker
        if tip_tracker[pip][0] == tip_tracker[pip][1]:
            protocol.pause("please replace tips.")
            pip.reset_tipracks()
            tip_tracker[pip][0] = 0
        pip.pick_up_tip()
        tip_tracker[pip][0] += 1

    # prepare mastermix (optional)
    if PREPARE_MASTERMIX:
        samp_overage = NUM_SAMPLES*1.1
        mm_vol = round(6.25*samp_overage, 2)
        assay_vol = round(1.25*samp_overage, 2)
        water_vol = round(11.25*samp_overage, 2)
        mmix = tube_block['A3']
        rnasep = tube_block['D2']
        water = tube_block['B3']
        rmixes = tube_block.wells()[4:7]

        protocol.comment('Preparing mastermixes...')

        pick_up(p300)
        for well in mm_wells:
            p300.transfer(mm_vol, mmix, well, new_tip='never')
            p300.blow_out()
        p300.drop_tip()

        for src, well in zip(rmixes, mm_wells):
            pick_up(p300)
            p300.transfer(water_vol, water, well, new_tip='never')
            p300.blow_out()
            p300.drop_tip()
            pick_up(p300)
            p300.transfer(assay_vol, rnasep, well, new_tip='never')
            p300.mix(5, 160, well)
            p300.blow_out()
            p300.drop_tip()
            pick_up(p300)
            p300.transfer(assay_vol, src, well, new_tip='never')
            p300.mix(10, 160, well)
            p300.blow_out()
            p300.drop_tip()

    # distribute mastermix
    protocol.comment('Distributing mastermix to strips...')
    col_vol = 21*num_cols
    for src, col in zip(mm_wells, mm_strip_single):
        pick_up(p300)
        for c in col:
            p300.transfer(col_vol, src, c, new_tip='never')
            p300.blow_out()
        p300.drop_tip()

    protocol.comment('Distributing mastermix to PCR plate...')
    for src, dest in zip(mm_strip, mm_cols):
        pick_up(m20)
        for col in dest:
            m20.transfer(20, src, col, new_tip='never')
            m20.blow_out()
        m20.drop_tip()

    # Add samples to PCR plate
    protocol.comment('Adding samples to PCR plate...')
    for dest in mm_cols:
        for samp, col in zip(samples, dest):
            pick_up(m20)
            m20.transfer(5, samp, col, new_tip='never')
            m20.mix(5, 15, col)
            m20.blow_out()
            m20.drop_tip()

    protocol.comment('Protocol complete!')
