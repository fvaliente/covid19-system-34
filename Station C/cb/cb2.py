import csv
import os

metadata = {
    'protocolName': 'CB2',
    'author': 'Chaz <protocols@opentrons.com>',
    'source': 'Custom Protocol Request',
    'apiLevel': '2.4'
}

TIP_TRACK = False
SAMPLE_TUBE = '1.5ml'  # can be '1.5ml' or '2ml'
VOL_15ML = 10  # volume in 15mL tube (in mL)
VOL_50ML = 25  # volume in 50mL tube (in mL)


def run(protocol):

    tips300 = [
        protocol.load_labware(
            'opentrons_96_filtertiprack_200ul', s) for s in ['4', '7', '10']]

    p300 = protocol.load_instrument(
        'p300_single_gen2', 'left', tip_racks=tips300)

    tubeRack = protocol.load_labware(
        'opentrons_10_tuberack_falcon_4x50ml_6x15ml_conical', '1')
    psuedovirus = tubeRack['A1']

    sampTRs = [
        protocol.load_labware(
            'opentrons_24_tuberack_eppendorf_'+SAMPLE_TUBE+'_safelock_snapcap', s) for s in ['6', '3']]

    finalPlate = protocol.load_labware('spl_96_wellplate_200ul', '2')

    # Tip tracking between runs
    if not protocol.is_simulating():
        file_path = '/data/csv/tiptrackingcb1.csv'
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

    t300count = int(tip_count_list[1])
    t300max = len(tips300)*96

    tip_tracker = {p300: [t300count, t300max]}

    def pick_up(pip):
        nonlocal tip_tracker
        if tip_tracker[pip][0] == tip_tracker[pip][1]:
            protocol.pause("please replace tips.")
            pip.reset_tipracks()
            tip_tracker[pip][0] = 0
        pip.pick_up_tip()
        tip_tracker[pip][0] += 1

    # starting height of liquid --> height = vol/pi*radius-squared
    ht15 = round(VOL_15ML*1000/(3.14*7.45**2), 2)
    ht50 = round(VOL_50ML*1000/(3.14*13.975**2), 2)
    hts = [ht15, ht50]

    # height tracking function
    def height_tracking(volume, tube):
        """
        This function tracks height in the 15/50mL tube.
        When a volume is entered, the distance from the bottom of the tube
        is recalculated.
        If the volume is low (and the pipette would crash),
        then the height is adjusted to the default height (1mm from bottom).
        """
        nonlocal hts

        if tube == 50:
            rad = 13.975
            height = hts[1]
        else:
            rad = 7.45
            height = hts[0]

        delta_ht = round((volume/1000/3.14*rad**2)*1.08, 2)

        height -= delta_ht

        if height < 1:
            height = 1

        if tube == 50:
            hts[1] = height
        else:
            hts[0] = height

    # distribute psuedovirus
    protocol.comment('Distributing psuedovirus...')
    p300vol = 0
    psuedowells = finalPlate.wells()
    del psuedowells[11:16]
    del psuedowells[3:8]
    pick_up(p300)
    for well in psuedowells:
        if p300vol == 0:
            p300.aspirate(200, psuedovirus.bottom(hts[0]))
            height_tracking(200, 15)
            p300vol = 200
        p300.dispense(50, well)
        p300vol -= 50
    p300.dispense(p300vol, psuedovirus.top(-5))
    p300.drop_tip()

    # add NC and VC to plate
    nc = sampTRs[1]['D5']
    vc = sampTRs[1]['D6']
    protocol.comment('Adding nc and vc...')
    for src, dest in zip([nc, vc], [finalPlate.rows()[x][:3] for x in range(2)]):
        for well in dest:
            pick_up(p300)
            p300.aspirate(50, src)
            p300.dispense(50, well)
            p300.blow_out()
            p300.drop_tip()

    sampwells = [well for plate in sampTRs for well in plate.wells()]
    sampchunks = [sampwells[i:i+8] for i in range(0, len(sampwells), 8)]

    protocol.comment('Adding samples...')
    for samp, col in zip(sampchunks, finalPlate.columns()[2::2]):
        for src, dest in zip(samp, col):
            pick_up(p300)
            p300.aspirate(50, src)
            p300.dispense(50, dest)
            p300.blow_out()
            p300.drop_tip()

    for samp, col in zip(sampchunks, finalPlate.columns()[3::2]):
        for src, dest in zip(samp, col):
            pick_up(p300)
            p300.aspirate(50, src)
            p300.dispense(50, dest)
            p300.blow_out()
            p300.drop_tip()
