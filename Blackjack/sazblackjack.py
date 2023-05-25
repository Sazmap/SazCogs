import re

import aiohttp
import asyncio
import math
from redbot.core import commands
from redbot.core import Config
import logging
import logging.handlers
import os
from copy import deepcopy
from datetime import datetime, timedelta
from random import shuffle
from enum import Enum



defaultCasinoConfig = {
    "Users": {}
}
    
defaultUserConfig = {
    "Chips" : 1000,
    "LastReset" : 0
    }
    
card_ranks = [_ for _ in range(2, 11)] + ['Jack', 'Queen', 'King', 'Ace']
card_suits = ['Spades', 'Hearts', 'Clubs', 'Diamonds']

def is_int(s):
    try:
        int(s)
        return True
    except ValueError:
        return False
        


def get_deck():
    return [Card(rank, suit) for rank in card_ranks for suit in card_suits] * 7
    #return [Card(rank, suit) for rank in ['Ace', 'Ace', 'Ace', 'Ace'] for suit in card_suits] * 7
 

class CasinoError(Exception):
    pass
    
class UserAlreadyExists(CasinoError):
    pass

class NotEnoughChips(CasinoError):
    pass

class UserDoesNotExist(CasinoError):
    pass
    
class InvalidInput(CasinoError):
    pass    

class UserNotPlaying(CasinoError):
    pass
    
class Card:
    def __init__(self, rank, suit):
        self.rank = rank
        self.suit = suit
    
    def __str__(self):
        retString = ""
        if self.rank in range(2, 11):
            retString += "{}".format(self.rank)
        else:
            retString += self.rank[0]
        
        retString += ":{}:".format(self.suit.lower())
        
        return retString
        
    def __eq__(self, other):
        if isinstance(other, Card):
            return self.rank == other.rank
        return NotImplemented
    
    
class BlackjackHand:

    def __init__(self, owner, bet):
        self.owner = owner
        self.bet = bet
        self.cards = []
        
    def __str__(self):
        retString = ""
        for i in self.cards:
            retString += "{} ".format(i)
        return retString
    
    def add_card(self, card):
        self.cards.append(card)
        
    def double_down(self):
        self.bet = self.bet * 2
        
    def remove_all_cards(self):
        self.cards = []
        
    def remove_card(self, index):
        return self.cards.pop(index)
    
    def get_owner(self):
        return self.owner
        
    def count_score(self):
        count = 0
        for i in self.cards:
            if i.rank in range(2, 11):
                count += i.rank
            elif i.rank != "Ace":
                count += 10
            else:
                count += 11
        
        if count > 21:
            for i in self.cards:
                if i.rank == "Ace":
                    count -= 10
                    if count <= 21:
                        break
        
        return count
      
    def count_score_low(self):
        count = 0
        for i in self.cards:
            if i.rank in range(2, 11):
                count += i.rank
            elif i.rank != "Ace":
                count += 10
            else:
                count += 1
                
        return count
        
class BlackjackInsurance:
    """Holds the insurance information"""
    def __init__(self, user, amount):
        self.user = user
        self.amount = amount

class GameStates(Enum):
    NotStarted = 0
    AcceptingBets = 1
    InProgress = 2
    InsuranceOpen = 3
    Payouts = 4
    
class BlackjackGame:
    """Actual game of blackjack. Holds current hands and current channel"""
    
    def __init__(self):
        self.currentDeck = []
        self.currentHands = []
        self.usedCards = []
        self.dealerHand = None
        self.currentPlayers = []
        self.currentChannel = None
        self.currentInsurance = []
    
        self.currentGamestate = GameStates.NotStarted
        pass    

    async def send(self, msg):
        if self.currentChannel:
            await self.currentChannel.send(msg)
    
    def add_card_to_hand(self, hand):
        card = self.currentDeck.pop()
        hand.add_card(card)
        self.usedCards.append(card)
        
    def deal_hands(self):
        self.currentGamestate = GameStates.InProgress
        for a in range(2):
            for i in self.currentHands:
                self.add_card_to_hand(i)
            self.add_card_to_hand(self.dealerHand)
        
    def user_insurance(self, user, amount):
        if user in [a.owner for a in self.currentHands]:
            if user not in [a.user for a in self.currentInsurance]:
                newInsurance = BlackjackInsurance(user, amount)
                self.currentInsurance.append(newInsurance)
        else:
            raise UserNotPlaying()
    
    def hit_hand(self, handIndex):
        self.add_card_to_hand(self.currentHands[handIndex])
    
    def get_hand(self, hand):
        return self.currentHands[hand]
        
    def get_num_hands(self):
        return len(self.currentHands)
    
    def get_hand_cards(self, hand):
        return self.currentHands[hand].cards
    
    def add_hand(self, owner, bet):
        newHand = BlackjackHand(owner, bet)
        self.currentHands.append(newHand)
        if owner not in self.currentPlayers:
            self.currentPlayers.append(owner)
        
    def remove_hand(self, hand):
        self.currentHands.pop(hand)
        
    def split_hand(self, hand):
        newHand = BlackjackHand(hand.owner, hand.bet)
        newHand.add_card(hand.remove_card(1))
        handIndex = self.currentHands.index(hand)
        self.currentHands.insert(handIndex + 1, newHand)
        self.hit_hand(handIndex)
        self.hit_hand(handIndex + 1)
        
    def new_game(self, channel = None):
        self.currentHands = []
        #if we've used a chunk of the deck shuffle it and put it on the end
        if(len(self.currentDeck) == 0):
            self.currentDeck = get_deck()
            shuffle(self.currentDeck)
        elif (len(self.usedCards) > 40):
            shuffle(self.usedCards)
            self.currentDeck += self.usedCards
            self.usedCards = []
        self.currentChannel = channel or self.currentChannel    
        self.dealerHand = BlackjackHand("Dealer", 0)
        self.currentInsurance = []
        self.currentPlayers = []
        self.currentGamestate = GameStates.AcceptingBets
        
    def open_insurance(self):
        self.currentGamestate = GameStates.InsuranceOpen
    
    def close_insurance(self):
        self.currentGamestate = GameStates.InProgress
    
    def double_down_hand(self, handIndex):
        self.currentHands[handIndex].double_down()
    
    def game_payouts(self):
        self.currentGamestate = GameStates.Payouts
    
    def game_end(self):
        self.currentGamestate = GameStates.NotStarted
    
    def get_gamestate(self):
        return self.currentGamestate
    
class ChipBank(commands.Cog):
    """Holds all the Casino data"""
    
    def __init__(self, bot):
        self.config = Config.get_conf(self, identifier=19028391723)
        self.config.register_user(Chips=1000, LastReset=0)
        self.bot = bot
    
    async def account_exists(self, user):
        user = await self.get_user(user)
        if user:
            return True
        return False
        
    async def get_user(self, user):
        ret = await self.config.user(user)()
        return ret
    
    async def get_user_balance(self, user):
        chips = await self.config.user(user).Chips()
        return chips

    async def add_user_balance(self, user, amount):
        add = int(round(amount))
        if add <= 0:
            raise InvalidInput()
        chips = await self.get_user_balance(user)
        new_value = chips + add
        await self.config.user(user).Chips.set(new_value)

    async def set_user_balance(self, user, amount):
        await self.config.user(user).Chips.set(amount)
    
    async def subtract_user_balance(self, user, amount):
        sub = int(round(amount))
        if sub <= 0:
            raise InvalidInput()
        chips = await self.get_user_balance(user)
        if sub > chips:
            raise NotEnoughChips()
        new_value = chips - sub
        await self.config.user(user).Chips.set(new_value)
        
    async def wipe_all_profile(self):
        await self.config.clear_all_members()
        
    def get_current_game(self):
        pass
    
class SazBlackjack(ChipBank):

    def __init__(self, bot):
        self.bot = bot
        super().__init__(self.bot)
        self.currentGame = BlackjackGame()
        self.timeLeft = 10
        self.blackJackTask = None
        self.context = None
                
    @commands.group(pass_context=True, no_pm=True, aliases=["bj", "21"])
    async def blackjack(self, ctx):
        """Blackjack Group Commands"""
        
        if ctx.invoked_subcommand is None:
            pass

    @blackjack.command(name="balance", pass_context=True, hidden=False)
    async def show_balance(self, ctx):
        """Displays your Blackjack balance"""
        user = ctx.message.author
        try:
            balance = await super().get_user_balance(user)
            await ctx.send("{}\n```Your balance is ${}```".format(user.mention, balance))
        except Exception as e:
            print(e)


    @blackjack.command(name="reset", pass_context=True, hidden=False)
    async def reset_balance(self, ctx):
        """Resets your balance to 1000"""
        if self.currentGame.currentGamestate == GameStates.NotStarted:
            user = ctx.message.author
            try:
                await self.set_user_balance(user, 1000)
                await ctx.send(f"Done.\n{user.mention}\n```Your balance is $1000```")
            except Exception as e:
                print(e)
        else:
            await ctx.send(f"This command can not be run during a game.")


    @blackjack.command(name="insurance", aliases=["ins"], pass_context=True, hidden=True)
    async def insurance_cmd(self, ctx, *params):
        """Signs up for insurance"""
        if self.currentGame.currentGamestate == GameStates.InsuranceOpen:
            user = ctx.message.author
        
            if (len(params) < 1):
                return await ctx.send("Invalid parameters.\n```USAGE: {}{} <amount>```".format(ctx.prefix, ctx.command, ctx.subcommand_passed))
                
            if not is_int(params[0]):
                return await ctx.send("Invalid parameters.\n```USAGE: {}{} <amount>```".format(ctx.prefix, ctx.command, ctx.subcommand_passed))
                
            try:
                self.currentGame.user_insurance(user, int(params[0]))    
                await ctx.send("Insurance of ${} purchased by {}.".format(params[0], user.mention))          
            except UserNotPlaying:
                return await ctx.send("Sorry {}, you have to be playing the current game to buy insurance.".format(user.mention))

            try:
                await super().subtract_user_balance(user, int(params[0]))
            except NotEnoughChips:
                return await ctx.send("You do not have enough chips to purchase insurance for that much.\n```Your balance is ${}```".format(await super().get_user_balance(user)))

        else:
            ctx.send("This command is not available right now.")
           
    @blackjack.command(name="bet", pass_context=True, hidden=False)
    async def blackjack_bet(self, ctx, *params):
        """Bets on the current game of Blackjack.\nUSAGE: [p]blackjack bet <amount> """
        user = ctx.message.author
        chanl = ctx.message.channel
        try:
            await super().get_user(user)
        except Exception as e:
            print(e)
            await ctx.send("No account for your user. Use {}{} create to create one.".format(ctx.prefix, ctx.command))
            return
        
        if (len(params) < 1):
            await ctx.send(f"Invalid parameters.\n```USAGE: {ctx.prefix}{ctx.command} <amount>```")
            return
        
        if not is_int(params[0]):
            await ctx.send(f"Invalid parameters.\n```USAGE: {ctx.prefix}{ctx.command} <amount>```")
            return
        
        bet = int(params[0])
        chips = await super().get_user_balance(user)
        
        try:
            await super().subtract_user_balance(user, bet)
        except NotEnoughChips:
            await ctx.send("You do not have enough chips to bet that much!\n```Your balance is: ${}```".format(chips))
            return
        except InvalidInput:
            await ctx.send("The amount entered must be positive!")
            return
        
        resetTimer = True
        
        if self.currentGame.get_gamestate() == GameStates.NotStarted:
            self.timeLeft = 10
            await self.start_game(chanl)
            self.context=ctx
            resetTimer = False
        
        if self.currentGame.get_gamestate() == GameStates.AcceptingBets:
            self.currentGame.add_hand(user, bet)
            if resetTimer == True:
                self.timeLeft = 10
                await ctx.send("A new bet has been placed! The game will start in {} seconds!".format(self.timeLeft))
        else:
            await ctx.send("Game is in progress - please wait for the current game to finish.")
            await super().add_user_balance(user, bet)
            
            
    async def start_game(self, channel):
        self.currentGame.new_game(channel)
        await channel.send("A new blackjack game has been started! Accepting new bets for the next {} seconds!\nResets are disabled while the game is running.".format(self.timeLeft))

        self.blackJackTask = self.bot.loop.create_task(self.start_new_game())

    async def start_new_game(self):
        await self.bot.wait_until_ready()
        try:
            while(self.timeLeft > 0):
                await asyncio.sleep(1)
                self.timeLeft = self.timeLeft - 1
            self.blackJackTask = self.bot.loop.create_task(self.play_blackjack())
        except asyncio.CancelledError:
            pass

    async def prompt_for_action(self, currentHand, allowedOptions):
        currentScore = currentHand.count_score()
        currentScoreLow = currentHand.count_score_low()
        if (currentScore != currentScoreLow):
            currentScoreText = "{} or {}".format(currentScore, currentScoreLow)
        else:
            currentScoreText = "{}".format(currentScore)

        await self.currentGame.send(
        "Your hand: {} ({})\nWhat would you like to do? ({})".format(
        currentHand,
        currentScoreText,
        ", ".join(allowedOptions)))

        def check(msg):
            return msg.channel == self.currentGame.currentChannel and msg.author == currentHand.owner and msg.content.lower() in [a.lower() for a in allowedOptions]
            
        try:
            choice = await self.bot.wait_for('message', timeout=10, check=check)
        except asyncio.TimeoutError:
            choice = None

        return choice

    """
    handle_hit
    Handles the process of a 'hit' game - hitting until one of a number of conditions
    Returns the number of hands removed (0 or 1)
    """
    async def handle_hit(self, currentHand, currentHandIndex):
        currentScore = currentHand.count_score()
        while(currentScore < 21):
            self.currentGame.hit_hand(currentHandIndex)
            currentScore = currentHand.count_score()
            currentScoreLow = currentHand.count_score_low()
            await self.currentGame.send(
            "Drew {}".format(currentHand.cards[-1]))
            if (currentScore == 21):
                await self.currentGame.send(
                "Your hand: {} ({})".format(
                currentHand,
                currentScoreText))
                return 0
                            
            if (currentScore > 21):
                await self.currentGame.send(
                "Bust! Your hand: {} ({})".format(
                currentHand,
                currentScore))
                self.currentGame.remove_hand(currentHandIndex)
                return 1
                
            if (len(currentHand.cards) == 5):
                await self.currentGame.send(
                "Five Card Charlie! You win!\nPayout is ${}\nYour hand: {} ({})".format(
                currentHand.bet,
                currentHand,
                currentScore))
                await super().add_user_balance(currentHand.owner, currentHand.bet * 2)
                self.currentGame.remove_hand(currentHandIndex)
                return 1

            choice = await self.prompt_for_action(currentHand, ["Stand", "Hit"])
            if choice is None or choice.content.casefold() == "stand".casefold():
                await self.currentGame.send(
                "Standing on {}.".format(currentScore))
                return 0
        return 0

            
    async def play_blackjack(self):
        await self.bot.wait_until_ready()
        try:

            mentionString = ""
            for i in self.currentGame.currentPlayers:
                mentionString += "{} ".format(i.mention)
                
            await self.currentGame.send("{}\nThe game is starting.\nDealing hands...".format(mentionString))
            self.currentGame.deal_hands()
            numHandsBJ = self.currentGame.get_num_hands()
            currentHandBJIndex = 0
            while currentHandBJIndex < numHandsBJ:
                currentBJHand = self.currentGame.get_hand(currentHandBJIndex)
                if currentBJHand.count_score() == 21:
                    await self.currentGame.send(self.currentGame.currentChannel, 
                    "{} got Blackjack!\nHand: {}\nPayout is ${}.".format(currentBJHand.owner.mention, currentBJHand, int(round(currentBJHand.bet*1.5))))
                    await super().add_user_balance(currentBJHand.owner, currentBJHand.bet + int(round(currentBJHand.bet * 1.5)))
                    self.currentGame.remove_hand(currentHandBJIndex)
                    #bit of a hack, but if an item is removed from the list of hands
                    #the loop needs to be fixed to not over-loop.
                    currentHandBJIndex -= 1
                    numHandsBJ -= 1
                currentHandBJIndex += 1
                
            currentHandIndex = 0
            numHands = self.currentGame.get_num_hands()
            
            if (self.currentGame.dealerHand.cards[1].rank == 'Ace'):
                await self.currentGame.send( 
                "Dealer showing {}\nInsurance is open for 10 seconds.\nSign up with {}{} insurance <amount>".format(
                self.currentGame.dealerHand.cards[1],
                self.context.prefix,
                self.context.command.parent))
                self.currentGame.open_insurance()
                await asyncio.sleep(10)
                await self.currentGame.send(
                "Insurance is now closed.")

            #even though insurance may not be open, this transitions to InProgress.
            self.currentGame.close_insurance()
            
            while currentHandIndex < numHands:
                currentHand = self.currentGame.get_hand(currentHandIndex)
                
                currentScore = currentHand.count_score()
                currentScoreLow = currentHand.count_score_low()
                
                
                allowedOptions = []
                allowedOptions.append("Stand")
                allowedOptions.append("Hit")
                if (await super().get_user_balance(currentHand.owner) >= currentHand.bet):
                    allowedOptions.append("Double")
                    if (currentHand.cards[0] == currentHand.cards[1]):
                        allowedOptions.append("Split")

                await self.currentGame.send(f"{currentHand.owner.mention}\nThe dealer shows: {self.currentGame.dealerHand.cards[1]}\n")

                choice = await self.prompt_for_action(currentHand, allowedOptions)


                if choice is None or choice.content.casefold() == "stand".casefold():
                    str = ""
                    await self.currentGame.send(
                    "Standing on {}.".format(currentScore))
                    
                elif choice.content.casefold() == "hit".casefold():
                    num_hands_removed = await self.handle_hit(currentHand, currentHandIndex)
                    #bit of a hack, but if an item is removed from the list of hands
                    #the loop needs to be fixed to not over-loop.
                    currentHandIndex -= num_hands_removed
                    numHands -= num_hands_removed

                
                elif choice.content.casefold() == "double".casefold():
                    await super().subtract_user_balance(currentHand.owner, currentHand.bet)
                    self.currentGame.hit_hand(currentHandIndex)
                    self.currentGame.double_down_hand(currentHandIndex)
                    await self.currentGame.send(
                    "Doubled down. Card will be revealed at the end of game.")
                
                elif choice.content.casefold() == "split".casefold():
                    await super().subtract_user_balance(currentHand.owner, currentHand.bet)
                    self.currentGame.split_hand(currentHand)
                    await self.currentGame.send(
                    "Hand split. You will play both hands one after another.")
                    numHands += 1
                    continue
                
                currentHandIndex += 1
                if currentHandIndex < numHands - 1:
                    await self.currentGame.send("Next Hand.")
            
            self.currentGame.game_payouts()
            
            dealerHand = self.currentGame.dealerHand
            
            dealerScore = dealerHand.count_score()

            await self.currentGame.send(
            "Dealer's hand: {} ({})".format(dealerHand, dealerScore))
            
            dealerBlackjack = False
            dealerBust = False
            
            if dealerScore == 21:
                dealerBlackjack = True
                await self.currentGame.send(
                "Dealer has Blackjack! All remaining hands lose.")
                #set dealerScore to 22 so all hands lose.
                dealerScore = 22
                
                for i in self.currentGame.currentInsurance:
                    
                    await self.currentGame.send(
                    "Paying out ${} to {} for insurance.".format(i.amount * 2, i.user.mention))
                    await super().add_user_balance(i.user, i.amount * 3)
            
            while dealerScore <= 16:    
                self.currentGame.add_card_to_hand(dealerHand)
                
                await self.currentGame.send(
                "Dealer hits\n")
                
                await asyncio.sleep(1)
                
                await self.currentGame.send(
                "Dealer Drew {}".format(dealerHand.cards[-1]))
                
                dealerScore = dealerHand.count_score()
                
                await self.currentGame.send(
                "Dealer has: {} ({})".format(dealerHand, dealerScore))
            
            
            if (dealerScore > 21
            and dealerBlackjack == False):
                await self.currentGame.send(
                "Dealer Busts! All remaining hands win.")
                dealerBust = True
                dealerScore = 0
            
            #resolve remaining hands
            for i in self.currentGame.currentHands:
                handScore = i.count_score()
                
                dealerScoreText = ""
                
                if dealerBlackjack == True:
                    dealerScoreText = "Blackjack!"
                elif dealerBust == True:
                    dealerScoreText = "Bust!"
                else:
                    dealerScoreText = "{}".format(dealerScore)
                
                await self.currentGame.send(
                "{}\nYou have: {} ({})\nDealer has: {} ({})".format(
                i.owner.mention,
                i,
                i.count_score(),
                dealerHand,
                dealerScoreText))
                
                #account for double down bust
                if handScore > 21:
                    handScore = -1
                
                if dealerScore < handScore:
                    await self.currentGame.send(
                    "You win! Paying out ${}".format(i.bet))
                    await super().add_user_balance(i.owner, i.bet * 2)
                    
                elif dealerScore > handScore:
                    await self.currentGame.send(
                    "You lose.")
                    
                elif handScore == dealerScore:
                    await self.currentGame.send(
                    "Push. Returning bet.")
                    await super().add_user_balance(i.owner, i.bet)
                
            await self.currentGame.send(
            "Game finished. Start a new game with {}{} bet <amount>.\nResets are now re-enabled.".format(
            self.context.prefix,
            self.context.command.parent))

            self.currentGame.game_end()
            
        except asyncio.CancelledError:
            pass
        
    def cog_unload(self):
        if self.blackJackTask is not None:
            self.blackJackTask.cancel()
