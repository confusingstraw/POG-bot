from discord import ui, SelectOption, ButtonStyle
import operator


def selected_bases(ctx, bases_list, callback):
    """ Returns a list of bases currently selected
    """

    options = list()

    bases_list = sorted(bases_list, key=operator.itemgetter('name'))

    for base in bases_list:
        description_args = list()
        emoji = '🟩'
        if base['was_played_recently']:
            emoji = '🟦'
            description_args.append("Recently played!")
        if base['is_booked']:
            emoji = '🟥'
            description_args.append("Currently booked!")

        if description_args:
            description = " ".join(description_args[::-1])
        else:
            description = None

        options.append(SelectOption(label=base['name'], description=description, emoji=emoji, value=base['id']))

    select = ui.Select(placeholder='Choose a base...', options=options, custom_id='base_selector')
    select.callback = callback
    # select.disabled = True
    view = ui.View(timeout=None)

    view.add_item(select)

    return view


def validation_view(ctx, callback):
    decline = ui.Button(label="Decline", style=ButtonStyle.red, custom_id='decline')
    accept = ui.Button(label="Accept", style=ButtonStyle.green, custom_id='accept')

    decline.callback = callback
    accept.callback = callback

    view = ui.View(timeout=None)

    view.add_item(accept)
    view.add_item(decline)

    return view
