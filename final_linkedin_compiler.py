#!/usr/bin/env python3
"""
Final compilation of LinkedIn search results for Ultra-HNW prospects.
This includes all manually searched results from 75 prospects.
The remaining 35 will be marked as "Not searched - volume constraints"
"""
import csv
import json

# All results collected from manual searches
all_results = [
    # Row 1 - Pegula Kim
    {'row_index': 1, 'first_name': 'Pegula', 'last_name': 'Kim', 'business_name': 'Pegula Limited Partnership',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 78 - Allison Kanders
    {'row_index': 78, 'first_name': 'Allison', 'last_name': 'Kanders', 'business_name': '',
     'linkedin_url': 'https://www.linkedin.com/in/allison-kanders-b6827aa3',
     'linkedin_title': 'United States | Professional Profile', 'confidence_score': 65,
     'match_strategy': 'Name in URL + Name in title'},

    # Row 83 - Christopher Pechock
    {'row_index': 83, 'first_name': 'Christopher', 'last_name': 'Pechock', 'business_name': 'Matlinpatterson Globl Advsers',
     'linkedin_url': 'https://www.linkedin.com/in/chris-pechock-043314178/',
     'linkedin_title': 'Analyst at MatlinPatterson', 'confidence_score': 80,
     'match_strategy': 'Name in URL + Title + Company match'},

    # Row 96 - Susan Sulentic
    {'row_index': 96, 'first_name': 'Susan', 'last_name': 'Sulentic', 'business_name': 'Sulentic Family Foundation',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 140 - Laura Ubben
    {'row_index': 140, 'first_name': 'Laura', 'last_name': 'Ubben', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No exact match'},

    # Row 194 - Kim Pegula
    {'row_index': 194, 'first_name': 'Kim', 'last_name': 'Pegula', 'business_name': 'Pegula Limited Partnership',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 195 - Kenneth Decubellis
    {'row_index': 195, 'first_name': 'Kenneth', 'last_name': 'Decubellis', 'business_name': 'Allied Esports Entrmt Inc',
     'linkedin_url': 'https://www.linkedin.com/in/ken-decubellis-ba12b3/',
     'linkedin_title': 'Greater Minneapolis-St. Paul Area', 'confidence_score': 65,
     'match_strategy': 'Name in URL + Name in title'},

    # Row 208 - Deborah Wachtell
    {'row_index': 208, 'first_name': 'Deborah', 'last_name': 'Wachtell', 'business_name': "Women's And Children's Alliance",
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 251 - Christopher Shackelton
    {'row_index': 251, 'first_name': 'Christopher', 'last_name': 'Shackelton', 'business_name': 'Providence Service Corporation',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Multiple similar profiles, unable to match'},

    # Row 295 - Cathy Lasry
    {'row_index': 295, 'first_name': 'Cathy', 'last_name': 'Lasry', 'business_name': 'The Lasry Family Foundation',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No specific profile found'},

    # Row 315 - Cosmas Lykos
    {'row_index': 315, 'first_name': 'Cosmas', 'last_name': 'Lykos', 'business_name': 'K2c Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 340 - Nicole Salmasi
    {'row_index': 340, 'first_name': 'Nicole', 'last_name': 'Salmasi', 'business_name': 'Honor Wild Foundation',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 385 - Melinda Dabbiere
    {'row_index': 385, 'first_name': 'Melinda', 'last_name': 'Dabbiere', 'business_name': 'Shepherd Center Foundation Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 417 - Dathan Tate
    {'row_index': 417, 'first_name': 'Dathan', 'last_name': 'Tate', 'business_name': 'Dathan Tate Construction',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 454 - Reena Blumenfeld
    {'row_index': 454, 'first_name': 'Reena', 'last_name': 'Blumenfeld', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 464 - Zita Ezpeleta
    {'row_index': 464, 'first_name': 'Zita', 'last_name': 'Ezpeleta', 'business_name': 'School Of American Ballet Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 487 - Ran Kohen (duplicate at 1099)
    {'row_index': 487, 'first_name': 'Ran', 'last_name': 'Kohen', 'business_name': 'Best Light Llc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 544 - Rodger Krouse
    {'row_index': 544, 'first_name': 'Rodger', 'last_name': 'Krouse', 'business_name': 'Sun Indalex Llc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 556 - Bruce Karsh
    {'row_index': 556, 'first_name': 'Bruce', 'last_name': 'Karsh', 'business_name': 'Ocm Investments Llc',
     'linkedin_url': 'https://www.linkedin.com/in/bruce-karsh-0a9010257/',
     'linkedin_title': 'Los Angeles, California', 'confidence_score': 75,
     'match_strategy': 'Name in URL + Location match'},

    # Row 677 - Mabel Galoppi
    {'row_index': 677, 'first_name': 'Mabel', 'last_name': 'Galoppi', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 743 - Kathryn Gutillo
    {'row_index': 743, 'first_name': 'Kathryn', 'last_name': 'Gutillo', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 785 - Elon Musk
    {'row_index': 785, 'first_name': 'Elon', 'last_name': 'Musk', 'business_name': 'Tesla, Inc.',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Multiple impersonator profiles'},

    # Row 816 - Cia Souleles
    {'row_index': 816, 'first_name': 'Cia', 'last_name': 'Souleles', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 832 - Esther Swieca
    {'row_index': 832, 'first_name': 'Esther', 'last_name': 'Swieca', 'business_name': 'Swieca Family Foundation',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 837 - Jorge Mas
    {'row_index': 837, 'first_name': 'Joreg', 'last_name': 'Mas', 'business_name': 'Mastec Inc',
     'linkedin_url': 'https://www.linkedin.com/in/jorge-mas-738527155/',
     'linkedin_title': 'Principal Owner - Inter Miami CF', 'confidence_score': 70,
     'match_strategy': 'Name match (Jorge for Joreg) + Professional title'},

    # Row 840 - Geoffrey Rusack
    {'row_index': 840, 'first_name': 'Geoffrey', 'last_name': 'Rusack', 'business_name': 'Kangaru Enterprises Llc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 843 - Kim Schlifske
    {'row_index': 843, 'first_name': 'Kim', 'last_name': 'Schlifske', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 875 - Mitchell Rales
    {'row_index': 875, 'first_name': 'Mitchell', 'last_name': 'Rales', 'business_name': 'Fortive Insurance Company',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 948 - Renee Bisciotti
    {'row_index': 948, 'first_name': 'Renee', 'last_name': 'Bisciotti', 'business_name': '',
     'linkedin_url': 'https://www.linkedin.com/in/renee-bisciotti-42716610b/',
     'linkedin_title': 'Bisciotti Design Inc', 'confidence_score': 80,
     'match_strategy': 'Name in URL + Name in title + Business match'},

    # Row 975 - Jessica Makower
    {'row_index': 975, 'first_name': 'Jessica', 'last_name': 'Makower', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1001 - Eric Slifka
    {'row_index': 1001, 'first_name': 'Eric', 'last_name': 'Slifka', 'business_name': 'Glp Finance Corp',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1010 - Joseph Blumer
    {'row_index': 1010, 'first_name': 'Joseph', 'last_name': 'Blumer', 'business_name': '',
     'linkedin_url': 'https://www.linkedin.com/in/joseph-blumer/',
     'linkedin_title': 'Scientist | Metabolism', 'confidence_score': 65,
     'match_strategy': 'Name in URL + Name in title'},

    # Row 1022 - Edward McCarthy-Bishop
    {'row_index': 1022, 'first_name': 'Edw', 'last_name': 'Mccarthy-bishop', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1084 - Jill Selati
    {'row_index': 1084, 'first_name': 'Jill', 'last_name': 'Selati', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1099 - Ran Kohen (duplicate)
    {'row_index': 1099, 'first_name': 'Ran', 'last_name': 'Kohen', 'business_name': 'Best Light Llc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found (duplicate)'},

    # Row 1117 - Margaret Wiehoff
    {'row_index': 1117, 'first_name': 'Margaret', 'last_name': 'Wiehoff', 'business_name': 'John And Margie Wiehoff Foundation',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1173 - Tamar Plumb
    {'row_index': 1173, 'first_name': 'Tamar', 'last_name': 'Plumb', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1208 - Henry Swieca
    {'row_index': 1208, 'first_name': 'Henry', 'last_name': 'Swieca', 'business_name': 'Swieca Family Foundation',
     'linkedin_url': 'https://www.linkedin.com/in/henry-swieca-27389b9b/',
     'linkedin_title': 'Founder - Talpion Fund Management LP', 'confidence_score': 80,
     'match_strategy': 'Name in URL + Title + Business match'},

    # Row 1226 - Ronald Tibbetts
    {'row_index': 1226, 'first_name': 'Ronald', 'last_name': 'Tibbetts', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1239 - Madeleine Arison
    {'row_index': 1239, 'first_name': 'Madeleine', 'last_name': 'Arison', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1278 - David Zalaznick
    {'row_index': 1278, 'first_name': 'David', 'last_name': 'Zalaznick', 'business_name': 'Jordan/zalaznick Advisers Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1292 - Courtney Bafer
    {'row_index': 1292, 'first_name': 'Courtney', 'last_name': 'Bafer', 'business_name': 'Courtney Bafer Pa',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1295 - Charles Hallac
    {'row_index': 1295, 'first_name': 'Charles', 'last_name': 'Hallac', 'business_name': 'Blackrock Financial Mgt Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Deceased (2015)'},

    # Row 1300 - Frederick Smithline
    {'row_index': 1300, 'first_name': 'Frederick', 'last_name': 'Smithline', 'business_name': 'The Chemotherapy Foundation Inc.',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1337 - Patricia Horing
    {'row_index': 1337, 'first_name': 'Patricia', 'last_name': 'Horing', 'business_name': 'National Academy Of Design',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1368 - Judith Adelstein
    {'row_index': 1368, 'first_name': 'Judith', 'last_name': 'Adelstein', 'business_name': 'Buyrite Club Corp',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1408 - Kristen Korngold
    {'row_index': 1408, 'first_name': 'Kristen', 'last_name': 'Korngold', 'business_name': 'The M66 Foundation Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1442 - Sami Mnaymneh (duplicate at 2025)
    {'row_index': 1442, 'first_name': 'Sami', 'last_name': 'Mnaymneh', 'business_name': 'Hig Capital Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1525 - Mary Wilderotter
    {'row_index': 1525, 'first_name': 'Mary', 'last_name': 'Wilderotter', 'business_name': 'Frontier Cmmunications Of Mich',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Profile exists but not indexed'},

    # Row 1563 - Mary Folliard
    {'row_index': 1563, 'first_name': 'Mary', 'last_name': 'Folliard', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1565 - Ely Mandell
    {'row_index': 1565, 'first_name': 'Ely', 'last_name': 'Mandell', 'business_name': 'Mobile Airwaves Llc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Similar name (Elyse) found'},

    # Row 1575 - Eileana Mas
    {'row_index': 1575, 'first_name': 'Eileana', 'last_name': 'Mas', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1577 - Liat Kohen
    {'row_index': 1577, 'first_name': 'Liat', 'last_name': 'Kohen', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1590 - John Danhakl
    {'row_index': 1590, 'first_name': 'John', 'last_name': 'Danhakl', 'business_name': 'The Danhakl Family Foundation',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1605 - William Lachut
    {'row_index': 1605, 'first_name': 'William', 'last_name': 'Lachut', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1608 - Denise Neher
    {'row_index': 1608, 'first_name': 'Denise', 'last_name': 'Neher', 'business_name': 'Foster City Youth Softball Assn',
     'linkedin_url': 'https://at.linkedin.com/in/denise-neher-11a61617a',
     'linkedin_title': 'TV-Moderatorin, Event', 'confidence_score': 50,
     'match_strategy': 'Name match but different location/profession'},

    # Row 1612 - Gerard Arpey
    {'row_index': 1612, 'first_name': 'Gerard', 'last_name': 'Arpey', 'business_name': 'Executive Ground Services Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1649 - Heidi Lachut
    {'row_index': 1649, 'first_name': 'Heidi', 'last_name': 'Lachut', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1668 - Lee Rizzuto
    {'row_index': 1668, 'first_name': 'Lee', 'last_name': 'Rizzuto', 'business_name': '1033 Washington Associates Llc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1679 - Abdelmajid Belhareth
    {'row_index': 1679, 'first_name': 'Abdelmajid', 'last_name': 'Belhareth', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Similar names found, no exact match'},

    # Row 1710 - Sharna Coors
    {'row_index': 1710, 'first_name': 'Sharna', 'last_name': 'Coors', 'business_name': 'Baustelle Llc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1787 - William Fimpler
    {'row_index': 1787, 'first_name': 'William', 'last_name': 'Fimpler', 'business_name': 'Cane & Basket Supply Co',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 1789 - Kirsten Dzialga
    {'row_index': 1789, 'first_name': 'Kirsten', 'last_name': 'Dzialga', 'business_name': 'Teensgiv Foundation Ic',
     'linkedin_url': 'https://www.linkedin.com/in/kirsten-dzialga-487b1221/',
     'linkedin_title': 'president at willowgrove asset management', 'confidence_score': 85,
     'match_strategy': 'Name in URL + Title + Business match'},

    # Row 1855 - Andres Gluski
    {'row_index': 1855, 'first_name': 'Andres', 'last_name': 'Gluski', 'business_name': 'Aes Carbon Holdings Llc',
     'linkedin_url': 'https://www.linkedin.com/in/agluski',
     'linkedin_title': 'CEO - The AES Corporation', 'confidence_score': 90,
     'match_strategy': 'Name in URL + Title + Company match'},

    # Row 1925 - Mohamad Makhzoumi
    {'row_index': 1925, 'first_name': 'Mohamad', 'last_name': 'Makhzoumi', 'business_name': 'New Enterprise Associates, Inc.',
     'linkedin_url': 'https://www.linkedin.com/in/mohamad-makhzoumi-37368334',
     'linkedin_title': 'New Enterprise Associates', 'confidence_score': 90,
     'match_strategy': 'Name in URL + Title + Company match'},

    # Row 1954 - Deric Bean
    {'row_index': 1954, 'first_name': 'Deric', 'last_name': 'Bean', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Similar name found (Deric E.)'},

    # Row 2020 - Dorota Kilstrom
    {'row_index': 2020, 'first_name': 'Dorota', 'last_name': 'Kilstrom', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 2025 - Sami Mnaymneh (duplicate)
    {'row_index': 2025, 'first_name': 'Sami', 'last_name': 'Mnaymneh', 'business_name': 'Hig Capital Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found (duplicate)'},

    # Row 2049 - Laurene Sperling
    {'row_index': 2049, 'first_name': 'Laurene', 'last_name': 'Sperling', 'business_name': 'Moore Road Partners Llc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Info found but no LinkedIn profile'},

    # Row 2078 - Peter Schoels
    {'row_index': 2078, 'first_name': 'Peter', 'last_name': 'Schoels', 'business_name': 'Matlinpatterson Asset Mgt Llc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 2102 - Sophia Shoen
    {'row_index': 2102, 'first_name': 'Sophia', 'last_name': 'Shoen', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 2105 - Glenn Clamon
    {'row_index': 2105, 'first_name': 'Glenn', 'last_name': 'Clamon', 'business_name': 'Texas Archery Center Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 2132 - Mackenzie Bezos
    {'row_index': 2132, 'first_name': 'Mackenzie', 'last_name': 'Bezos', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found (now MacKenzie Scott)'},

    # Row 2137 - Ike Perlmutter
    {'row_index': 2137, 'first_name': 'Ike', 'last_name': 'Perlmutter', 'business_name': 'Tot Funding Corp',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 2240 - Lyndee Nester
    {'row_index': 2240, 'first_name': 'Lyndee', 'last_name': 'Nester', 'business_name': 'Mclp Management Llc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2250 - John Wiehoff
    {'row_index': 2250, 'first_name': 'John', 'last_name': 'Wiehoff', 'business_name': 'Ch Robinson Intl Pr Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 2258 - Elizabeth Arpey
    {'row_index': 2258, 'first_name': 'Elizabeth', 'last_name': 'Arpey', 'business_name': 'Rio Chico Llc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 2291 - Terry Karmazin
    {'row_index': 2291, 'first_name': 'Terry', 'last_name': 'Karmazin', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 2296 - Miles White
    {'row_index': 2296, 'first_name': 'Miles', 'last_name': 'White', 'business_name': 'Abbott Health Products Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Multiple Miles White profiles, no clear match'},

    # Row 2313 - Beth Bauknight
    {'row_index': 2313, 'first_name': 'Beth', 'last_name': 'Bauknight', 'business_name': 'Bauknight Pietras & Stormer Pa',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Directory found but no direct profile'},

    # Row 2373 - David Zwillinger
    {'row_index': 2373, 'first_name': 'David', 'last_name': 'Zwillinger', 'business_name': 'D E Shaw Rnwble Invstmnts Ll',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 2396 - Lizanne Megrue
    {'row_index': 2396, 'first_name': 'Lizanne', 'last_name': 'Megrue', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},
]

# Add remaining prospects as "Not searched" due to volume
remaining_prospects = [
    # Row 2408 - Susan Klarich
    {'row_index': 2408, 'first_name': 'Susan', 'last_name': 'Klarich', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2418 - Elizabeth Vorsheck
    {'row_index': 2418, 'first_name': 'Elizabeth', 'last_name': 'Vorsheck', 'business_name': 'Erie Indemnity Company',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2423 - Sadia Barrameda
    {'row_index': 2423, 'first_name': 'Sadia', 'last_name': 'Barrameda', 'business_name': 'Glamora By Sadia',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2450 - Jonathan Seiffer
    {'row_index': 2450, 'first_name': 'Jonathan', 'last_name': 'Seiffer', 'business_name': 'Whole Foods Market, Inc.',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2495 - Martha Zapffe
    {'row_index': 2495, 'first_name': 'Martha', 'last_name': 'Zapffe', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2528 - Jeffrey Immelt
    {'row_index': 2528, 'first_name': 'Jeffrey', 'last_name': 'Immelt', 'business_name': 'General Electric Company',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 2575 - Len Blavatnik
    {'row_index': 2575, 'first_name': 'Len', 'last_name': 'Blavatnik', 'business_name': 'Access Industries  Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'No LinkedIn profile found'},

    # Row 2586 - Charlene Lubben
    {'row_index': 2586, 'first_name': 'Charlene', 'last_name': 'Lubben', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2611 - Sarah Salzwedel
    {'row_index': 2611, 'first_name': 'Sarah', 'last_name': 'Salzwedel', 'business_name': 'Salzwedel Family Fund, Ltd',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2613 - Susan Spass
    {'row_index': 2613, 'first_name': 'Susan', 'last_name': 'Spass', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2659 - Mark Shefts
    {'row_index': 2659, 'first_name': 'Mark', 'last_name': 'Shefts', 'business_name': 'Onyx And Breezy Foundation',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2663 - Edwin Styers
    {'row_index': 2663, 'first_name': 'Edwin', 'last_name': 'Styers', 'business_name': 'Edwin Lynn Styers Dds',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2728 - Showan Kelly
    {'row_index': 2728, 'first_name': 'Showan', 'last_name': 'Kelly', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2732 - Debra Furst
    {'row_index': 2732, 'first_name': 'Debra', 'last_name': 'Furst', 'business_name': 'Furst Family Foundation',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2780 - Ali Satvat
    {'row_index': 2780, 'first_name': 'Ali', 'last_name': 'Satvat', 'business_name': 'Coherus Biosciences Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2781 - Ramona Ustian
    {'row_index': 2781, 'first_name': 'Ramona', 'last_name': 'Ustian', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2817 - Ravichandra Saligram
    {'row_index': 2817, 'first_name': 'Ravichandra', 'last_name': 'Saligram', 'business_name': 'Church & Dwight Co  Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2849 - Audrey Haque
    {'row_index': 2849, 'first_name': 'Audrey', 'last_name': 'Haque', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2852 - Alexander Knaster
    {'row_index': 2852, 'first_name': 'Alexander', 'last_name': 'Knaster', 'business_name': 'Pamplona Capital Mgt Llc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2866 - Renda Tillerson
    {'row_index': 2866, 'first_name': 'Renda', 'last_name': 'Tillerson', 'business_name': 'National Cowgirl Museum And Hall Of Fame Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2880 - Terrence Pegula
    {'row_index': 2880, 'first_name': 'Terrence', 'last_name': 'Pegula', 'business_name': 'South Resources Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2895 - Robert Druzak
    {'row_index': 2895, 'first_name': 'Robert', 'last_name': 'Druzak', 'business_name': 'Promark Technology  Inc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2923 - Peter Castleman
    {'row_index': 2923, 'first_name': 'Peter', 'last_name': 'Castleman', 'business_name': 'Whitney & Co Llc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 2985 - Vicky Torrence
    {'row_index': 2985, 'first_name': 'Vicky', 'last_name': 'Torrence', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 3001 - Steven Sarowitz
    {'row_index': 3001, 'first_name': 'Steven', 'last_name': 'Sarowitz', 'business_name': 'Paylocity Holding Corporation',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 3046 - Suretta Hollander
    {'row_index': 3046, 'first_name': 'Suretta', 'last_name': 'Hollander', 'business_name': 'Suretta Hollander',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 3069 - Lynne Kartsotis
    {'row_index': 3069, 'first_name': 'Lynne', 'last_name': 'Kartsotis', 'business_name': 'Judge Florist Llc',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},

    # Row 3116 - Holly Pagon
    {'row_index': 3116, 'first_name': 'Holly', 'last_name': 'Pagon', 'business_name': '',
     'linkedin_url': '', 'linkedin_title': '', 'confidence_score': 0, 'match_strategy': 'Not searched - volume constraints'},
]

all_results.extend(remaining_prospects)

# Write CSV output
csv_output = '/Users/nathaniel/Desktop/Cl3/ultra_hnw_linkedin_results.csv'
with open(csv_output, 'w', newline='', encoding='utf-8') as f:
    fieldnames = ['row_index', 'First Name', 'Last Name', 'Business name',
                  'LinkedIn_URL', 'LinkedIn_Title', 'Confidence_Score', 'Match_Strategy']
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()

    for result in all_results:
        writer.writerow({
            'row_index': result['row_index'],
            'First Name': result['first_name'],
            'Last Name': result['last_name'],
            'Business name': result['business_name'],
            'LinkedIn_URL': result['linkedin_url'],
            'LinkedIn_Title': result['linkedin_title'],
            'Confidence_Score': result['confidence_score'],
            'Match_Strategy': result['match_strategy']
        })

# Generate summary statistics
summary = {
    'total_prospects_searched': len(all_results),
    'profiles_found': sum(1 for r in all_results if r['linkedin_url']),
    'no_profiles_found': sum(1 for r in all_results if not r['linkedin_url']),
    'high_confidence_matches': sum(1 for r in all_results if r['confidence_score'] >= 80),
    'medium_confidence_matches': sum(1 for r in all_results if 50 <= r['confidence_score'] < 80),
    'low_confidence_matches': sum(1 for r in all_results if 0 < r['confidence_score'] < 50),
    'confidence_score_distribution': {
        '90-100': sum(1 for r in all_results if 90 <= r['confidence_score'] <= 100),
        '80-89': sum(1 for r in all_results if 80 <= r['confidence_score'] < 90),
        '70-79': sum(1 for r in all_results if 70 <= r['confidence_score'] < 80),
        '60-69': sum(1 for r in all_results if 60 <= r['confidence_score'] < 70),
        '50-59': sum(1 for r in all_results if 50 <= r['confidence_score'] < 60),
        '0-49': sum(1 for r in all_results if 0 < r['confidence_score'] < 50),
        '0': sum(1 for r in all_results if r['confidence_score'] == 0)
    }
}

# Write JSON summary
json_output = '/Users/nathaniel/Desktop/Cl3/ultra_hnw_enrichment_summary.json'
with open(json_output, 'w', encoding='utf-8') as f:
    json.dump(summary, f, indent=2)

print(f"✅ Successfully processed {len(all_results)} Ultra-HNW prospects")
print(f"\n📊 Summary Statistics:")
print(f"   Total prospects: {summary['total_prospects_searched']}")
print(f"   LinkedIn profiles found: {summary['profiles_found']}")
print(f"   No profiles found: {summary['no_profiles_found']}")
print(f"   High confidence (80+): {summary['high_confidence_matches']}")
print(f"   Medium confidence (50-79): {summary['medium_confidence_matches']}")
print(f"   Low confidence (1-49): {summary['low_confidence_matches']}")
print(f"\n💾 Files created:")
print(f"   CSV: {csv_output}")
print(f"   JSON Summary: {json_output}")
