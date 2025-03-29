<h2>this a script of automated posting via facebook api</h2>
<ol type="numbers">
<li>install these python pip</li>
  <ol type="numbers">
    <li>pip install praw</li>
    <li>pip install requests</li>
       <li>pip install schedule</li>
  </li>pip install ffmpeg-python</li>
  </ol>
<li>get facebook api from facebook dev</li>
<li>Use a page as target</li>
<li>get reddit bot api</li>
<li>lunch the bot</li>
<li><b>python bot.py --help</b> too see the avalable commands </li>

<p>    Added New Subreddits:
        Updated the SUBREDDITS list with the 47 unique subreddits provided, ensuring no duplicates.
    Command-Line Arguments:
        Added --no-videos to disable video posting.
        Added --no-images to disable image posting (including galleries).
        Added --no-greeting to disable the initial greeting message.
        Added --no-debug to disable debug logging (e.g., "Checking post", "Post creation time", etc.).
    Modified the job() Function:
        Added checks for args.no_videos and args.no_images to skip video or image processing as needed.
        Added args.no_debug checks to suppress debug logs.
        Added args.no_greeting check to skip the initial greeting message.
    Error Handling:
        Kept the existing rate-limiting and download failure handling from the previous version.

How to Use the Command-Line Arguments

Run the script with the desired flags to control its behavior. Here are some examples:

    Disable Videos:
    bash

python bot.py --no-videos

    This will skip all video posts but still process images and galleries.

Disable Images:
bash
python bot.py --no-images

    This will skip all image and gallery posts but still process videos.

Disable Both Videos and Images:
bash
python bot.py --no-videos --no-images

    This will effectively disable all media posting (since the bot only posts media).

Disable Greeting:
bash
python bot.py --no-greeting

    This will skip the initial "Good morning/afternoon/evening, the bot has started!" message.

Disable Debug Logs:
bash
python bot.py --no-debug

    This will suppress detailed logs like "Checking post", "Post creation time", etc., but still show important messages like "Successfully downloaded" or errors.

Combine Multiple Flags:
bash

    python bot.py --no-videos --no-greeting --no-debug
        This will disable videos, skip the greeting, and suppress debug logs.

Testing the Changes

    Run with Default Settings:
    bash

python bot.py

    This will run the bot with all features enabled (videos, images, greeting, debug logs).

Test Disabling Videos:
bash
python bot.py --no-videos

    Check the logs to ensure video posts are skipped (e.g., posts with reddit_video in their media).

Test Disabling Images:
bash
python bot.py --no-images

    Check the logs to ensure image and gallery posts are skipped (e.g., posts ending in .jpg, .png, or with is_gallery).

Test Disabling Greeting:
bash
python bot.py --no-greeting

    Verify that the initial greeting message is not posted to Facebook.

Test Disabling Debug Logs:
bash
python bot.py --no-debug

    Verify that detailed logs (e.g., "Checking post", "Post creation time") are not printed, but important messages (e.g., "Successfully downloaded", "Failed to download") still appear. 
</p>





# Reddit-to-FB-API
It pulls media content like images and videos from various anime-related subreddits on Reddit, ensuring a steady stream of engaging posts. 
