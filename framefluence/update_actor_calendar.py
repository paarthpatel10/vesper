import csv
import datetime
import os

# 30 Evergreen Legends (Will remain still)
EVERGREEN_ACTORS = [
    {
        "name": "Christian Bale",
        "birth_date": "1974-01-30",
        "roles": "The Dark Knight Trilogy, American Psycho, The Prestige, The Machinist",
        "hook": "The greatest method actor in cinema history turns [AGE] today. Here are his 4 most insane transformations."
    },
    {
        "name": "Leonardo DiCaprio",
        "birth_date": "1974-11-11",
        "roles": "The Wolf of Wall Street, Inception, Shutter Island, The Revenant",
        "hook": "Happy Birthday Leonardo DiCaprio! The uncut glass scene that proved he was a madman..."
    },
    {
        "name": "Cillian Murphy",
        "birth_date": "1976-05-25",
        "roles": "Oppenheimer, Peaky Blinders, Inception, Dunkirk",
        "hook": "The cold gaze that captivated cinema. Happy Birthday to Cillian Murphy 🥃"
    },
    {
        "name": "Ryan Gosling",
        "birth_date": "1980-11-12",
        "roles": "Blade Runner 2049, Drive, La La Land, The Nice Guys",
        "hook": "He's literally me. Happy Birthday to Ryan Gosling 🚗 3 scenes that define quiet confidence."
    },
    {
        "name": "Matthew McConaughey",
        "birth_date": "1969-11-04",
        "roles": "Interstellar, True Detective, Dallas Buyers Club, The Wolf of Wall Street",
        "hook": "The video message scene in Interstellar. Happy Birthday Matthew McConaughey 🚀"
    },
    {
        "name": "Brad Pitt",
        "birth_date": "1963-12-18",
        "roles": "Fight Club, Inglourious Basterds, Se7en, Once Upon a Time in Hollywood",
        "hook": "Happy Birthday Brad Pitt. The 3 rules Tyler Durden taught a generation."
    },
    {
        "name": "Tom Cruise",
        "birth_date": "1962-07-03",
        "roles": "Mission: Impossible, Top Gun: Maverick, Edge of Tomorrow, Collateral",
        "hook": "The last true Hollywood movie star. 4 real stunts that almost took his life."
    },
    {
        "name": "Keanu Reeves",
        "birth_date": "1964-09-02",
        "roles": "The Matrix, John Wick, Constantine, Speed",
        "hook": "The most humble man in Hollywood turns [AGE]. 3 reasons everyone loves Keanu Reeves."
    },
    {
        "name": "Al Pacino",
        "birth_date": "1940-04-25",
        "roles": "The Godfather, Scarface, Heat, Scent of a Woman",
        "hook": "Happy Birthday Al Pacino. The legendary diner scene with De Niro in Heat."
    },
    {
        "name": "Robert De Niro",
        "birth_date": "1943-08-17",
        "roles": "Taxi Driver, Goodfellas, Raging Bull, The Irishman",
        "hook": "'You talkin' to me?' Happy Birthday to the cinema titan, Robert De Niro."
    },
    {
        "name": "Denzel Washington",
        "birth_date": "1954-12-28",
        "roles": "Training Day, The Equalizer, Flight, Malcolm X",
        "hook": "'King Kong ain't got sh*t on me!' Happy Birthday to Denzel Washington 👑"
    },
    {
        "name": "Joaquin Phoenix",
        "birth_date": "1974-10-28",
        "roles": "Joker, Her, Gladiator, The Master",
        "hook": "The bathroom dance that was 100% improvised. Happy Birthday Joaquin Phoenix 🃏"
    },
    {
        "name": "Heath Ledger",
        "birth_date": "1979-04-04",
        "roles": "The Dark Knight, Brokeback Mountain, 10 Things I Hate About You",
        "hook": "Remembering Heath Ledger. The hospital explosion scene that defined cinematic villainy."
    },
    {
        "name": "Jake Gyllenhaal",
        "birth_date": "1980-12-19",
        "roles": "Nightcrawler, Prisoners, Donnie Darko, Zodiac",
        "hook": "The mirror punch was completely unscripted. Happy Birthday Jake Gyllenhaal 🎥"
    },
    {
        "name": "Tom Hardy",
        "birth_date": "1977-09-15",
        "roles": "The Dark Knight Rises, Mad Max: Fury Road, Warrior, Inception",
        "hook": "Happy Birthday Tom Hardy. Acting with only his eyes in Bane and Mad Max."
    },
    {
        "name": "Christoph Waltz",
        "birth_date": "1956-10-04",
        "roles": "Inglourious Basterds, Django Unchained, Spectre",
        "hook": "The opening 15 minutes of Inglourious Basterds. Happy Birthday Christoph Waltz 🥛"
    },
    {
        "name": "Anthony Hopkins",
        "birth_date": "1937-12-31",
        "roles": "The Silence of the Lambs, The Father, Westworld",
        "hook": "Only 16 minutes on screen, won an Oscar. Happy Birthday Sir Anthony Hopkins 🍷"
    },
    {
        "name": "Morgan Freeman",
        "birth_date": "1937-06-01",
        "roles": "The Shawshank Redemption, Se7en, The Dark Knight",
        "hook": "The voice of cinema. Happy Birthday to Morgan Freeman 🎙️ 'Get busy living...'"
    },
    {
        "name": "Bryan Cranston",
        "birth_date": "1956-03-07",
        "roles": "Breaking Bad, Drive, Malcolm in the Middle, Trumbo",
        "hook": "'I am the one who knocks.' Happy Birthday Bryan Cranston 🧪"
    },
    {
        "name": "Javier Bardem",
        "birth_date": "1969-03-01",
        "roles": "No Country for Old Men, Skyfall, Dune, Biutiful",
        "hook": "The gas station coin toss scene. Happy Birthday to cinema's most terrifying villain."
    },
    {
        "name": "Mads Mikkelsen",
        "birth_date": "1965-11-22",
        "roles": "Hannibal, Casino Royale, The Hunt, Another Round",
        "hook": "Happy Birthday Mads Mikkelsen 🍷 The ending dance in Another Round is pure cinema."
    },
    {
        "name": "Gary Oldman",
        "birth_date": "1958-03-21",
        "roles": "The Dark Knight, Leon: The Professional, Darkest Hour, Harry Potter",
        "hook": "Cinema's greatest chameleon. Happy Birthday Gary Oldman 🎭"
    },
    {
        "name": "Edward Norton",
        "birth_date": "1969-08-18",
        "roles": "Fight Club, American History X, Primal Fear, Birdman",
        "hook": "The courtroom twist in Primal Fear. Happy Birthday Edward Norton 🥊"
    },
    {
        "name": "Robert Downey Jr.",
        "birth_date": "1965-04-04",
        "roles": "Oppenheimer, Iron Man, Sherlock Holmes, Tropic Thunder",
        "hook": "From rock bottom to Oscar winner. Happy Birthday Robert Downey Jr. 💥"
    },
    {
        "name": "Hugh Jackman",
        "birth_date": "1968-10-12",
        "roles": "Logan, The Prestige, Prisoners, Les Misérables",
        "hook": "24 years playing Wolverine. Happy Birthday Hugh Jackman 🐺"
    },
    {
        "name": "Henry Cavill",
        "birth_date": "1983-05-05",
        "roles": "Mission: Impossible - Fallout, Man of Steel, The Witcher",
        "hook": "The arm reload in Mission Impossible Fallout. Happy Birthday Henry Cavill 💪"
    },
    {
        "name": "Willem Dafoe",
        "birth_date": "1955-07-22",
        "roles": "Spider-Man, The Lighthouse, Poor Things, Platoon",
        "hook": "'Hark Triton, hark!' Happy Birthday Willem Dafoe 🦞 3 times he stole the movie."
    },
    {
        "name": "Michael Fassbender",
        "birth_date": "1977-04-02",
        "roles": "Inglourious Basterds, Shame, X-Men: Days of Future Past, The Killer",
        "hook": "The 3 fingers in the tavern scene. Happy Birthday Michael Fassbender 🍻"
    },
    {
        "name": "Colin Farrell",
        "birth_date": "1976-05-31",
        "roles": "The Banshees of Inisherin, The Batman (Penguin), In Bruges, The Lobster",
        "hook": "The most underrated dramatic actor working today. Happy Birthday Colin Farrell 🐧"
    },
    {
        "name": "Andrew Garfield",
        "birth_date": "1983-08-20",
        "roles": "The Social Network, Tick Tick Boom, Hacksaw Ridge, Spider-Man",
        "hook": "'Sorry my Prada's at the cleaners!' Happy Birthday Andrew Garfield 💻"
    }
]

# 20 Trending / Modern Generation Stars (Updated based on current Hollywood momentum)
TRENDING_ACTORS = [
    {
        "name": "Timothée Chalamet",
        "birth_date": "1995-12-27",
        "roles": "Dune, Wonka, Call Me by Your Name, Bones and All",
        "hook": "Leading this generation of cinema. Happy Birthday Timothée Chalamet 🏜️"
    },
    {
        "name": "Pedro Pascal",
        "birth_date": "1975-04-02",
        "roles": "The Last of Us, The Mandalorian, Gladiator II, Narcos",
        "hook": "The internet's favorite star turns [AGE]. 3 iconic Pedro Pascal performances."
    },
    {
        "name": "Austin Butler",
        "birth_date": "1991-08-17",
        "roles": "Dune: Part Two (Feyd-Rautha), Elvis, The Bikeriders, Masters of the Air",
        "hook": "Feyd-Rautha in black & white. Happy Birthday Austin Butler ⚔️"
    },
    {
        "name": "Glen Powell",
        "birth_date": "1988-10-21",
        "roles": "Twisters, Hit Man, Top Gun: Maverick, Anyone But You",
        "hook": "Bringing back the 90s leading man charisma. Happy Birthday Glen Powell 🌪️"
    },
    {
        "name": "Jacob Elordi",
        "birth_date": "1997-06-26",
        "roles": "Saltburn, Priscilla, Euphoria, Frankenstein",
        "hook": "Happy Birthday Jacob Elordi. 3 scenes showing his dramatic screen presence."
    },
    {
        "name": "Paul Mescal",
        "birth_date": "1996-02-02",
        "roles": "Gladiator II, Aftersun, Normal People, All of Us Strangers",
        "hook": "From indie heartbreak to the Colosseum. Happy Birthday Paul Mescal ⚔️"
    },
    {
        "name": "Barry Keoghan",
        "birth_date": "1992-10-18",
        "roles": "The Banshees of Inisherin, Saltburn, The Batman, Dunkirk",
        "hook": "Cinema's most unpredictable actor. Happy Birthday Barry Keoghan 🪓"
    },
    {
        "name": "Florence Pugh",
        "birth_date": "1996-01-03",
        "roles": "Oppenheimer, Midsommar, Dune: Part Two, Little Women",
        "hook": "Happy Birthday Florence Pugh 🌸 3 times she completely stole the scene."
    },
    {
        "name": "Zendaya",
        "birth_date": "1996-09-01",
        "roles": "Dune, Challengers, Euphoria, Spider-Man",
        "hook": "Happy Birthday Zendaya 🎾 The intensity in Challengers proved her range."
    },
    {
        "name": "Margot Robbie",
        "birth_date": "1990-07-02",
        "roles": "The Wolf of Wall Street, Babylon, Barbie, Once Upon a Time in Hollywood",
        "hook": "The audition slap that landed her Wolf of Wall Street. Happy Birthday Margot Robbie 💅"
    },
    {
        "name": "Anya Taylor-Joy",
        "birth_date": "1996-04-16",
        "roles": "Furiosa: A Mad Max Saga, The Queen's Gambit, The Witch, The Menu",
        "hook": "Communicating pure fury without saying a word. Happy Birthday Anya Taylor-Joy 🔥"
    },
    {
        "name": "Sydney Sweeney",
        "birth_date": "1997-09-12",
        "roles": "Euphoria, Immaculate, Anyone But You, The White Lotus",
        "hook": "Happy Birthday Sydney Sweeney 🩸 The scream in the finale of Immaculate."
    },
    {
        "name": "Jenna Ortega",
        "birth_date": "2002-09-27",
        "roles": "Wednesday, Beetlejuice Beetlejuice, Scream VI, X",
        "hook": "The new scream queen. Happy Birthday Jenna Ortega 🖤"
    },
    {
        "name": "Jeremy Allen White",
        "birth_date": "1991-02-17",
        "roles": "The Bear, The Iron Claw, Shameless",
        "hook": "'Yes Chef!' Happy Birthday Jeremy Allen White 🔪 3 high-intensity monologue scenes."
    },
    {
        "name": "Robert Pattinson",
        "birth_date": "1986-05-13",
        "roles": "The Batman, The Lighthouse, Good Time, Tenet",
        "hook": "'I am vengeance.' Happy Birthday Robert Pattinson 🦇 3 dark indie roles that redeemed him."
    },
    {
        "name": "Emma Stone",
        "birth_date": "1988-11-06",
        "roles": "Poor Things, La La Land, The Favourite, Cruella",
        "hook": "Two-time Oscar winner before 36. Happy Birthday Emma Stone 💃"
    },
    {
        "name": "Ana de Armas",
        "birth_date": "1988-04-30",
        "roles": "Blade Runner 2049, Knives Out, No Time to Die, Blonde",
        "hook": "'You look like a good Joe.' Happy Birthday Ana de Armas in Blade Runner 2049 🌧️"
    },
    {
        "name": "Mia Goth",
        "birth_date": "1993-10-25",
        "roles": "Pearl, X, MaXXXine, Infinity Pool",
        "hook": "The 9-minute unblinking smile. Happy Birthday Mia Goth 🪓 Modern horror queen."
    },
    {
        "name": "Aaron Taylor-Johnson",
        "birth_date": "1990-06-13",
        "roles": "Bullet Train, Nocturnal Animals, Kraven, Tenet",
        "hook": "The terrifying villain in Nocturnal Animals. Happy Birthday Aaron Taylor-Johnson 🚅"
    },
    {
        "name": "Sebastian Stan",
        "birth_date": "1982-08-13",
        "roles": "The Apprentice, A Different Man, Captain America: Winter Soldier, Pam & Tommy",
        "hook": "From Winter Soldier to prestige indie transformer. Happy Birthday Sebastian Stan ⚡"
    }
]

def generate_actor_calendar(output_csv_path):
    today = datetime.date.today()
    all_actors = []

    for item in EVERGREEN_ACTORS:
        all_actors.append({
            "name": item["name"],
            "birth_date": item["birth_date"],
            "tier": "Evergreen Famous",
            "roles": item["roles"],
            "hook": item["hook"]
        })

    for item in TRENDING_ACTORS:
        all_actors.append({
            "name": item["name"],
            "birth_date": item["birth_date"],
            "tier": "Trending / Modern",
            "roles": item["roles"],
            "hook": item["hook"]
        })

    rows = []
    for a in all_actors:
        b_year, b_month, b_day = map(int, a["birth_date"].split("-"))
        # Month name + day
        b_date_obj = datetime.date(2000, b_month, b_day)
        month_day_str = b_date_obj.strftime("%B %d")

        # Age in current year
        age_now = today.year - b_year

        # Days until next birthday
        this_year_bday = datetime.date(today.year, b_month, b_day)
        if this_year_bday < today:
            next_bday = datetime.date(today.year + 1, b_month, b_day)
            age_on_bday = (today.year + 1) - b_year
        else:
            next_bday = this_year_bday
            age_on_bday = today.year - b_year

        days_until = (next_bday - today).days

        # Weekly / Monthly Priority category
        if days_until <= 7:
            priority = "🔥 CRITICAL: Next 7 Days!"
        elif days_until <= 30:
            priority = "⚡ UPCOMING: Next 30 Days"
        elif days_until <= 60:
            priority = "📅 IN QUEUE: Next 60 Days"
        else:
            priority = "⏳ Future"

        # Format personalized hook with real age
        hook_formatted = a["hook"].replace("[AGE]", str(age_on_bday))

        rows.append({
            "Days_Until_Birthday": days_until,
            "Actor_Name": a["name"],
            "Tier_Type": a["tier"],
            "Birthday_Month_Day": month_day_str,
            "Birth_Year": b_year,
            "Next_Birthday_Date": next_bday.strftime("%Y-%m-%d"),
            "Age_Turning": age_on_bday,
            "Weekly_Priority": priority,
            "Signature_Movies_Or_Roles": a["roles"],
            "Birthday_Reel_Hook": hook_formatted
        })

    # Sort so upcoming birthdays are right at the very top!
    rows.sort(key=lambda x: x["Days_Until_Birthday"])

    fieldnames = [
        "Days_Until_Birthday",
        "Actor_Name",
        "Tier_Type",
        "Birthday_Month_Day",
        "Birth_Year",
        "Next_Birthday_Date",
        "Age_Turning",
        "Weekly_Priority",
        "Signature_Movies_Or_Roles",
        "Birthday_Reel_Hook"
    ]

    with open(output_csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"Top 50 Actor Calendar generated successfully at: {output_csv_path}")
    print(f"Total Actors: {len(rows)} (30 Evergreen + 20 Trending)")

    # Print upcoming in next 30 days
    print("\n--- UPCOMING ACTOR BIRTHDAYS (NEXT 30 DAYS) ---")
    upcoming = [r for r in rows if r["Days_Until_Birthday"] <= 30]
    for u in upcoming:
        print(f"[{u['Days_Until_Birthday']} days] {u['Actor_Name']} ({u['Birthday_Month_Day']}, turns {u['Age_Turning']}) - {u['Tier_Type']}")

def main():
    from framefluence.paths import ACTOR_CALENDAR
    generate_actor_calendar(ACTOR_CALENDAR)


if __name__ == "__main__":
    main()
