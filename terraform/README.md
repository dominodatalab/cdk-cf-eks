
# Manual CloudFormation Bootstrap

While you can use cdk itself to deploy, should you want to deploy it in
CloudFormation without the tool (perhaps preparing the CloudFormation
beforehand and deploying it with some other automation), it does require
some minor preparation and some extra parameters.

This terraform is for mamually bootstrapping the CloudFormation output of CDK
in this fashion. It can be used as-is, or taken as an example for your own
implementation.

Instructions for deploying fully by hand are also provided below, though doing
so introduces more possibility for human error.

The most important steps are the preparation beforehand.

## Generate CloudFormation and associated Assets

Run "cdk synth" to generate CloudFormation from cdk. You can set the output directory to something specific with `-o`, otherwise it defaults to generating a subdirectory `cdk.out`.

 cdk synth -o output\_dir

`cdk synth` will generate a number of assets with the filename `asset.<HASH>`, as well as some json files (including the CloudFormation manifest). Some of the `asset.<HASH>` files will be zip files, others will be directories that need to be zipped up.

## Deploying to CloudFormation with Terraform

The terraform module has a handful of arguments. Most are basic, but the asset parameters must be generated accurately.

### Terraform module parameters

* asset\_bucket: The name of the bucket to be created by terraform, which will hold the assets/cloudformation manifest
* asset\_dir: The directory that `cdk synth` output to. By default this is `cdk.out`, or overridden with `-o` to be `output_dir` in the previous example.
* aws\_region: The region to be deployed into. This must match the region given in the Domino CDK config
* name: The unique name of the deployment. This must match the name given in the Domino CDK config
* parameters: Extra parameters to give to the CloudFormation stack. This *must* include all asset parameters that CDK generates. Using the helper command below, we will generate them for you. To understand how they're generated, see the subsection "Determine asset parameters" in the "Manual Preparation" section
* template\_filename: The name of the CloudFormation template in the asset directory. It will usually be `yourname-eks-stack.template.json`
* output\_dir: Directory where the agent\_template.yaml and EKS cluster kubeconfig will be written to. Must be full path.

### Generating a Terraform module configuration

There is a helper command `generate_terraform_bootstrap` in `app.py` that you can use to generate a Terraform configuration utilizing this module:

 python3 app.py generate\_terraform\_bootstrap /path/to/this/module your-asset-bucket-name aws-region your-deployment-name yourname-eks-stack /path/to/outputs

This command will prepare the asset directory (some files need to be zipped), determine the proper asset prameters, and then finally generate the config for the terraform module and print it to standard out. This terraform config can be used as-is to deploy your CDK CloudFormation stack.

#### Example output

    /cdk-cf-eks/# python3 app.py generate\_terraform\_bootstrap ./terraform my-bucket /assetdir us-west-2 exampledomino yourname-eks-stack /path/to/outputs
    {
        "module": {
            "cdk": {
                "source": "/cdk-cf-eks/terraform",
                "asset_bucket": "my-bucket",
                "asset_dir": "/assetdir",
                "aws_region": "us-west-2",
                "name": "exampledomino",
                "parameters": {
                    "AssetParameters4cd61014b71160e8c66fe167e43710d5ba068b80b134e9bd84508cf9238b2392ArtifactHashE56CD69A": "4cd61014b71160e8c66fe167e43710d5ba068b80b134e9bd84508cf9238b2392",
                    "AssetParameters4cd61014b71160e8c66fe167e43710d5ba068b80b134e9bd84508cf9238b2392S3BucketBF7A7F3F": "my-bucket",
                    "AssetParameters4cd61014b71160e8c66fe167e43710d5ba068b80b134e9bd84508cf9238b2392S3VersionKeyFAF93626": "||asset.4cd61014b71160e8c66fe167e43710d5ba068b80b134e9bd84508cf9238b2392.zip",
                    # [...]
                    "AssetParameters57a2bc4f0e42d7dbe3f7903543c088ff5c0a155a1bf983682c348ffc278f02e1ArtifactHash122F010D": "57a2bc4f0e42d7dbe3f7903543c088ff5c0a155a1bf983682c348ffc278f02e1",
                    "AssetParameters57a2bc4f0e42d7dbe3f7903543c088ff5c0a155a1bf983682c348ffc278f02e1S3Bucket4D55F912": "my-bucket",
                    "AssetParameters57a2bc4f0e42d7dbe3f7903543c088ff5c0a155a1bf983682c348ffc278f02e1S3VersionKey6E4430B5": "||eksstackawscdkawseksKubectlProviderE4B47DF2.nested.template.json"
                },
                "template_filename": "yourname-eks-stack-1620763317.template.json"
                "output_dir": "/path/to/outputs"
            }
        }
    }

### Note about upgrading

Terraform will not detect changes inside the CloudFormation template contents, but it will trigger on filename changes. To facilitate upgrades, the helper function will copy the template file to one with a timestamp and input that into the terraform module (ie `yourname-eks-stack-<timestamp>.template.json`). If you want to disable this functionality, add an additional argument "True" to the `generate_terraform_bootstrap` command, like so:

 python3 app.py generate\_terraform\_bootstrap ./terraform my-bucket /assetdir us-west-2 exampledomino yourname-eks-stack /path/to/outputs True

### Example commands for a full session

    cd /cdk-cf-eks/
    cp /tmp/prepared-config.yaml ./config.yaml
    cdk synth -o /assetdir
    mkdir /terraform
    python3 app.py generate\_terraform\_bootstrap ./terraform my-bucket /assetdir us-west-2 mydomino yourname-eks-stack /path/to/outputs > /terraform/main.tf.json
    cd /terraform
    terraform init
    terraform plan -out terraform.plan
    terraform apply terraform.plan

## Manual preparation

Like with the Terraform instructions, you'll need to configure your cdk stack and run `cdk synth`.

## Prepare asset directory

We have provided a helper command to prepare the asset directory and determine the parameters. There are also more barebones instructions following this to better illustrate what's being done, but we recommend using the helper command to reduce human error.

 python3 app.py generate\_asset\_parameters /assetdir my-bucket yourname-eks-stack

This command will prepare the asset directory by zipping up certain directories into zip files, determine the correct asset parameters, and then print them to the screen:

    {
        "AssetParameters4cd61014b71160e8c66fe167e43710d5ba068b80b134e9bd84508cf9238b2392ArtifactHashE56CD69A": "4cd61014b71160e8c66fe167e43710d5ba068b80b134e9bd84508cf9238b2392",
        "AssetParameters4cd61014b71160e8c66fe167e43710d5ba068b80b134e9bd84508cf9238b2392S3BucketBF7A7F3F": "my-bucket",
        "AssetParameters4cd61014b71160e8c66fe167e43710d5ba068b80b134e9bd84508cf9238b2392S3VersionKeyFAF93626": "||asset.4cd61014b71160e8c66fe167e43710d5ba068b80b134e9bd84508cf9238b2392.zip",
        [...] # etc.
        "AssetParameters57a2bc4f0e42d7dbe3f7903543c088ff5c0a155a1bf983682c348ffc278f02e1ArtifactHash122F010D": "57a2bc4f0e42d7dbe3f7903543c088ff5c0a155a1bf983682c348ffc278f02e1",
        "AssetParameters57a2bc4f0e42d7dbe3f7903543c088ff5c0a155a1bf983682c348ffc278f02e1S3Bucket4D55F912": "my-bucket",
        "AssetParameters57a2bc4f0e42d7dbe3f7903543c088ff5c0a155a1bf983682c348ffc278f02e1S3VersionKey6E4430B5": "||eksstackawscdkawseksKubectlProviderE4B47DF2.nested.template.json"
    }

### Fully manual instructions

#### Manually zip asset directories

Enter your asset directory

    cd /assetdir

And zip up every asset that was created as a directory of files

    find . -maxdepth 1 \! -path . -type d | xargs -I % bash -c "cd % && zip -9r ../%.zip ./"

#### Determine asset parameters

The CloudFormation will require several arbitrarily-named parameters for each one of these `asset.HASH` files as input.

Here is a `jq` command that can be used to determine the parameters:

    jq -r '.artifacts."cdktest5-eks-stack".metadata."/cdktest5-eks-stack"[] | select(.type == "aws:cdk:asset") | .data | "\(.artifactHashParameter)=\(.sourceHash)\n\(.s3KeyParameter)=||\(.path)\n\(.s3BucketParameter)=yourbucketname"' assetdir/manifest.json | sed -E '/\.(zip|json)$/! s/(VersionKey.*)/\1.zip/'

It'll produce output like this:

    AssetParameters4cd61014b71160e8c66fe167e43710d5ba068b80b134e9bd84508cf9238b2392ArtifactHashE56CD69A=4cd61014b71160e8c66fe167e43710d5ba068b80b134e9bd84508cf9238b2392
    AssetParameters4cd61014b71160e8c66fe167e43710d5ba068b80b134e9bd84508cf9238b2392S3VersionKeyFAF93626=||asset.4cd61014b71160e8c66fe167e43710d5ba068b80b134e9bd84508cf9238b2392
    AssetParameters4cd61014b71160e8c66fe167e43710d5ba068b80b134e9bd84508cf9238b2392S3BucketBF7A7F3F=yourbucketname
    AssetParameters50e10880d134a01b440991fc77d217f39f01c2d56945215ee9a3b81187c6f3b1ArtifactHash32F5D823=50e10880d134a01b440991fc77d217f39f01c2d56945215ee9a3b81187c6f3b1
    AssetParameters50e10880d134a01b440991fc77d217f39f01c2d56945215ee9a3b81187c6f3b1S3VersionKey85C003F9=||asset.50e10880d134a01b440991fc77d217f39f01c2d56945215ee9a3b81187c6f3b1
    AssetParameters50e10880d134a01b440991fc77d217f39f01c2d56945215ee9a3b81187c6f3b1S3Bucket36C546E0=yourbucketname
    [...]

And all of these parameters it produces are required inputs into cloudformation.

## Deploying CloudFormation

At this point, the assets need to be uploaded to an S3 bucket. Using our instructions, they must be in the root of your bucket. The "S3VersionKey" has the file path and can be modified to use a prefix path by putting the path before the double pipes (`||`).

When you create your cloudformation stack, link to the `yourname-eks-stack.template.json` file in the s3 bucket, include all of the parameters generated in the previous step, as well as the parameter "name" (which should match the "name" parameter you used to create your cdk assets).
