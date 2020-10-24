from opentrons import types
import math


metadata = {
    'protocolName': 'MGI Extraction (200µl sample input)',
    'author': 'Chaz <chaz@opentrons.com>',
    'apiLevel': '2.4'
}

NUM_SAMPLES = 16
# start with 8 samples, slowly increase to 48, then 94 (max is 94)
ELUTION_VOL = 60
STARTING_VOL = 200


# Start protocol
def run(ctx):
    # load labware and pipettes
    num_cols = math.ceil(NUM_SAMPLES/8)
    tips300 = [ctx.load_labware('opentrons_96_tiprack_300ul', slot, '200µl filtertiprack')
               for slot in ['6', '9', '3', '11', '10', '8']]

    all_tips = [tr['A'+str(i)] for tr in tips300 for i in range(1, 13)]
    [tips1, tips2, tips3, tips4, tips5] = [
        all_tips[i:i+num_cols] for i in range(0, num_cols*5, num_cols)
        ]

    m300 = ctx.load_instrument(
        'p300_multi_gen2', 'left', tip_racks=tips300)

    magdeck = ctx.load_module('magnetic module gen2', '4')
    magdeck.disengage()
    magheight = 6.0
    magplate = magdeck.load_labware('nest_96_wellplate_2ml_deep')
    tempdeck = ctx.load_module('Temperature Module Gen2', '1')
    flatplate = tempdeck.load_labware('opentrons_96_aluminumblock_nest_wellplate_100ul',)
    waste = ctx.load_labware('nest_1_reservoir_195ml', '7','Liquid Waste').wells()[0].top()
    """
    Second waste container for runs of 96 samples
    waste2 = ctx.load_labware('nest_1_reservoir_195ml', '8',
                             'Liquid Waste').wells()[0].top()"""
    """
    res2 = ctx.load_labware(
        'nest_12_reservoir_15ml', '2', 'reagent reservoir 2')
    res1 = ctx.load_labware(
        'nest_12_reservoir_15ml', '5', 'reagent reservoir 1')
    # Uncomment. Use this for 22mL reservoir
    """
    res2 = ctx.load_labware(
        'usascientific_12_reservoir_22ml', '2', 'reagent reservoir 1')
    res1 = ctx.load_labware(
        'usascientific_12_reservoir_22ml', '5', 'reagent reservoir 1')


    magbuff = [well for well in res1.wells()[:4] for _ in range(3)][:num_cols]
    wb1 = [well for well in res1.wells()[4:8] for _ in range(3)][:num_cols]
    wb2 = [well for well in res1.wells()[8:] for _ in range(3)][:num_cols]
    etoh = [well for well in res2.wells()[:6] for _ in range(2)][:num_cols]
    water = res2.wells()[-1]

    magsamps = magplate.rows()[0][:num_cols]
    elution_samps = flatplate.rows()[0][:num_cols]

    magdeck.disengage()  # just in case
    # tempdeck.set_temperature(4)  # uncomment for amb. temp.

    m300.flow_rate.aspirate = 50
    m300.flow_rate.dispense = 150
    m300.flow_rate.blow_out = 300

    x_offset = [1, -1] * 6

    def init_well_mix(reps, loc, vol):
        loc1 = loc.bottom().move(types.Point(x=1, y=0, z=0.6))
        loc2 = loc.bottom().move(types.Point(x=1, y=0, z=5.5))
        loc3 = loc.bottom().move(types.Point(x=-1, y=0, z=0.6))
        loc4 = loc.bottom().move(types.Point(x=-1, y=0, z=5.5))
        m300.aspirate(20, loc1)
        for _ in range(reps-1):
            m300.aspirate(vol, loc1)
            m300.dispense(vol, loc4)
            m300.aspirate(vol, loc3)
            m300.dispense(vol, loc2)
        m300.dispense(20, loc2)

    def well_mix(reps, loc, vol, side):
        opp_side = side * -1
        loc1 = loc.bottom().move(types.Point(x=side, y=0, z=0.6))
        loc2 = loc.bottom().move(types.Point(x=opp_side, y=0, z=4))
        m300.aspirate(20, loc2)
        mvol = vol-20
        for _ in range(reps-1):
            m300.aspirate(mvol, loc2)
            m300.dispense(mvol, loc1)
        m300.dispense(20, loc2)

    # transfer 460ul of Buffer Mixture
    ctx.comment('Adding buffer mixture to samples:')
    m300.pick_up_tip()
    for well, reagent, tip in zip(magsamps, magbuff, tips1):
        for _ in range(2):
            m300.aspirate(155, reagent)
            m300.dispense(155, well.top(-5))
        #    m300.aspirate(10, well.top(-5))  # aspirate from samples???
        m300.aspirate(150, reagent)
        m300.dispense(170, well.top(-10))
    m300.drop_tip()
    
    for well, tip, side in zip(magsamps, tips1, x_offset):
        m300.pick_up_tip()
        init_well_mix(2, well, 160)
        m300.blow_out()
        m300.drop_tip()
    
    # to add to 10 minute incubation - not needed for 48+ samples
    ctx.delay(seconds=20)

    magdeck.engage(height=magheight)
    ctx.comment('Incubating on magdeck for 2 minutes')
    ctx.delay(seconds=300)

    def supernatant_removal(vol, src, dest, side):
        s = side * -1
        m300.flow_rate.aspirate = 20
        tvol = vol
        asp_ctr = 0
        while tvol > 180:
            m300.aspirate(
                180, src.bottom().move(types.Point(x=s, y=0, z=0.5)))
            m300.dispense(180, dest)
            m300.aspirate(10, dest)
            tvol -= 180
            asp_ctr += 1
        m300.aspirate(
            tvol, src.bottom().move(types.Point(x=s, y=0, z=0.5)))
        dvol = 10*asp_ctr + tvol
        m300.dispense(dvol, dest)
        m300.flow_rate.aspirate = 50

    # Remove supernatant
    ctx.comment('Removing supernatant:')
    removal_vol = STARTING_VOL + 460

    for well, tip, side in zip(magsamps, tips1, x_offset):
        m300.pick_up_tip()
        supernatant_removal(removal_vol, well, waste, side)
        m300.drop_tip()

    magdeck.disengage()

    def wash_step(src, vol, mtimes, tips, usedtips, msg, trash_tips=True):
        ctx.comment(f'Wash Step {msg} - Adding reagent to samples:')
        for well, tip, tret, s, x in zip(magsamps, tips, usedtips, src, x_offset):
            m300.pick_up_tip()
            asp_ctr2 = 0
            mvol = vol
            while mvol > 200:
                m300.aspirate(200, s)
                m300.dispense(200, well.top(-3))
                #m300.aspirate(10, well.top(-3))
                asp_ctr2 += 1
                mvol -= 200
            m300.aspirate(mvol, s)
            dvol = 10*asp_ctr2 + mvol
            m300.dispense(dvol, well.bottom(5))
            well_mix(mtimes, well, 180, x)
            m300.blow_out()
            m300.drop_tip()

        magdeck.engage(height=magheight)
        ctx.comment('Incubating on MagDeck for 3 minutes.')
        ctx.delay(seconds=180)

        ctx.comment(f'Removing supernatant from Wash {msg}:')
        svol = vol+40
        for well, tip, x in zip(magsamps, usedtips, x_offset):
            m300.pick_up_tip()
            supernatant_removal(svol, well, waste, x)
            m300.aspirate(20, waste)
            m300.drop_tip()
        magdeck.disengage()

    wash_step(wb1, 500, 2, tips2, tips1, '1 Wash Buffer 1')

    wash_step(wb2, 500, 2, tips3, tips2, '2 Wash Buffer 2')

    wash_step(etoh, 600, 2, tips4, tips3, '3 Ethanol Wash')

    ctx.comment('Allowing beads to air dry for 5 minutes.')
    ctx.delay(seconds=300)

    m300.flow_rate.aspirate = 20
    ctx.comment('Removing any excess ethanol from wells:')

    # Add water for elution
    ctx.comment('Adding NF-water to wells for elution:')
    #t_vol = ELUTION_VOL + 20
    for well, tip, tret, x in zip(magsamps, tips5, tips4, x_offset):
        m300.pick_up_tip()
        #m300.aspirate(20, water.top())
        m300.aspirate(ELUTION_VOL, water)
        for _ in range(4):
            m300.dispense(
                ELUTION_VOL, well.bottom().move(types.Point(x=x, y=0, z=2)))
            m300.aspirate(
                ELUTION_VOL, well.bottom().move(types.Point(x=x, y=0, z=0.5)))
        m300.dispense(ELUTION_VOL, well)
        m300.blow_out()
        m300.drop_tip()

    ctx.comment('Incubating at room temp for 10 minutes.')
    ctx.delay(seconds=300)

    # Step 21 - Transfer elutes to clean plate
    magdeck.engage(height=magheight)
    ctx.comment('Incubating on MagDeck for 2 minutes.')
    ctx.delay(seconds=300)

    ctx.comment('Transferring elution to final plate:')
    m300.flow_rate.aspirate = 10
    final_vol = ELUTION_VOL - 5
    for src, dest, tip, x in zip(magsamps, elution_samps, tips5, x_offset):
        s = x * -1
        m300.pick_up_tip()
        m300.aspirate(final_vol, src.bottom().move(types.Point(x=s, y=0, z=0.6)))
        m300.dispense(final_vol, dest)
        m300.drop_tip()

    magdeck.disengage()

    ctx.comment('Congratulations! The protocol is complete')
